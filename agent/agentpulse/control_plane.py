"""Dependency-free AgentPulse SaaS control-plane client.

Credentials are stored outside JSON config in a strict mode-0600 regular file.
Network failures are returned as data so monitoring/remediation never crashes
because the SaaS control plane is unavailable.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

_MAX_RESPONSE_BYTES = 65536
_MODE_RANK = {"off": 0, "alert": 1, "ask": 2, "auto": 3}


class CredentialError(ValueError):
    """Credential file is absent or violates ownership/mode requirements."""


class ControlPlaneError(RuntimeError):
    """Enrollment or policy retrieval failed."""


@dataclass(frozen=True)
class PushResult:
    ok: bool
    status: int
    error: str = ""
    duplicate: bool = False


def write_credential(path: str, credential: str) -> None:
    """Atomically write one agent credential with mode 0600."""
    if not isinstance(credential, str) or not credential or "\n" in credential:
        raise CredentialError("agent credential is invalid")
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".agentpulse-credential-", dir=parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(credential)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def read_credential(path: str) -> str:
    """Read a mode-0600 regular file without following symlinks."""
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise CredentialError("agent credential file is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise CredentialError("agent credential file must be a regular file")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise CredentialError("agent credential file must have mode 0600")
    if info.st_size < 1 or info.st_size > 4096:
        raise CredentialError("agent credential file has an invalid size")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            value = handle.read(4097).strip()
    except OSError as exc:
        raise CredentialError("agent credential file could not be read safely") from exc
    if not value or len(value) > 4096 or "\n" in value:
        raise CredentialError("agent credential file contains invalid data")
    return value


def _request_json(
    url: str,
    method: str,
    authorization: str,
    payload: Optional[Dict[str, Any]],
    timeout: int,
    opener: Callable[..., Any],
) -> Tuple[int, Dict[str, Any]]:
    data = None if payload is None else json.dumps(
        payload, separators=(",", ":")
    ).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer " + authorization,
        "User-Agent": "AgentPulse/0.1",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url, data=data, headers=headers, method=method
    )
    try:
        response = opener(request, timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response as handle:
        status_code = int(getattr(handle, "status", getattr(handle, "code", 0)))
        raw = handle.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ControlPlaneError("control-plane response exceeded size limit")
    if not raw:
        return status_code, {}
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControlPlaneError("control-plane returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ControlPlaneError("control-plane response must be an object")
    return status_code, decoded


def _error_code(payload: Dict[str, Any], default: str) -> str:
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    return default


def enroll(
    base_url: str,
    enrollment_token: str,
    agent_key: str,
    hostname: str,
    local_policy_ceiling: str,
    credential_file: str,
    timeout: int = 10,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Dict[str, Any]:
    """Exchange a one-time enrollment token and persist the agent credential."""
    status_code, response = _request_json(
        base_url.rstrip("/") + "/v1/agents/enroll",
        "POST",
        enrollment_token,
        {
            "agent_key": agent_key,
            "hostname": hostname,
            "local_policy_ceiling": local_policy_ceiling,
        },
        timeout,
        opener,
    )
    if status_code != 201:
        raise ControlPlaneError(_error_code(response, "enrollment_failed"))
    credential = response.get("agent_credential")
    if not isinstance(credential, str) or not credential.startswith("ap_agent_"):
        raise ControlPlaneError("control-plane omitted a valid agent credential")
    write_credential(credential_file, credential)
    safe = dict(response)
    safe.pop("agent_credential", None)
    return safe


def _bounded_incidents(state: Dict[str, Any]) -> list:
    incidents = []
    history = state.get("history", [])
    if isinstance(history, list):
        for entry in history[-25:]:
            if isinstance(entry, dict):
                incidents.append({
                    "kind": str(entry.get("action", "event"))[:128],
                    "status": str(entry.get("outcome", "recorded"))[:64],
                    "detail": str(entry.get("reason", entry.get("target", "")))[:1024],
                })
    pending = state.get("pending", {})
    values = list(pending.values()) if isinstance(pending, dict) else (
        pending if isinstance(pending, list) else []
    )
    for entry in values[: max(0, 50 - len(incidents))]:
        if isinstance(entry, dict):
            incidents.append({
                "kind": str(entry.get("action", "pending"))[:128],
                "status": "pending",
                "detail": str(entry.get("target", ""))[:1024],
            })
    return incidents[:50]


def push_heartbeat(
    base_url: str,
    credential_file: str,
    state: Dict[str, Any],
    summary: Dict[str, Any],
    cycle_id: str,
    timeout: int = 10,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> PushResult:
    """Push one bounded heartbeat; return failures without raising."""
    try:
        credential = read_credential(credential_file)
        observed = state.get("last_run")
        if not isinstance(observed, (int, float)):
            observed = time.time()
        status_code, response = _request_json(
            base_url.rstrip("/") + "/v1/agents/heartbeat",
            "POST",
            credential,
            {
                "idempotency_key": str(cycle_id)[:128],
                "observed_at": float(observed),
                "summary": dict(summary),
                "incidents": _bounded_incidents(state),
            },
            timeout,
            opener,
        )
        if status_code in (200, 202):
            return PushResult(
                ok=True,
                status=status_code,
                duplicate=bool(response.get("duplicate", False)),
            )
        return PushResult(
            ok=False,
            status=status_code,
            error=_error_code(response, "heartbeat_rejected"),
        )
    except Exception as exc:  # network/control plane must never stop local safety loop
        return PushResult(ok=False, status=0, error=exc.__class__.__name__)


def _narrow(value: Any, ceiling: str) -> Any:
    if isinstance(value, list):
        return [_narrow(item, ceiling) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "mode" and item in _MODE_RANK:
            result[key] = ceiling if _MODE_RANK[item] > _MODE_RANK[ceiling] else item
        else:
            result[key] = _narrow(item, ceiling)
    return result


def fetch_policy(
    base_url: str,
    credential_file: str,
    local_ceiling: str,
    timeout: int = 10,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Dict[str, Any]:
    """Fetch remote policy and independently enforce the host ceiling."""
    if local_ceiling not in _MODE_RANK:
        raise ControlPlaneError("invalid local policy ceiling")
    credential = read_credential(credential_file)
    status_code, response = _request_json(
        base_url.rstrip("/") + "/v1/agents/policy",
        "GET",
        credential,
        None,
        timeout,
        opener,
    )
    if status_code != 200:
        raise ControlPlaneError(_error_code(response, "policy_fetch_failed"))
    policy = response.get("policy", {})
    safe = dict(response)
    safe["policy"] = _narrow(policy, local_ceiling)
    return safe
