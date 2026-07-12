"""Stable agent identity, enrollment, and local credential storage.

Identity is a UUID persisted independently from hostname. Credentials are kept
in a separate strict-permission file and are never included in status output.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
import tempfile
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from . import __version__
from .control_plane import read_credential, write_credential


class IdentityError(RuntimeError):
    """Identity or enrollment operation failed safely."""


class IdentityManager:
    def __init__(self, identity_path: os.PathLike[str] | str, credential_path: os.PathLike[str] | str) -> None:
        self.identity_path = Path(identity_path)
        self.credential_path = Path(credential_path)

    def ensure_agent_id(self, hostname: Optional[str] = None) -> str:
        """Load the stable UUID, creating it atomically on first use."""
        data = self._read_identity()
        agent_id = data.get("agent_id")
        if not isinstance(agent_id, str):
            agent_id = str(uuid.uuid4())
        if hostname is not None and data.get("hostname") != hostname:
            data["hostname"] = hostname
        data["agent_id"] = agent_id
        self._write_identity(data)
        return agent_id

    def store_credential(self, credential: str) -> None:
        write_credential(str(self.credential_path), credential)

    def read_credential(self) -> str:
        return read_credential(str(self.credential_path))

    def rotate_credential(self, credential: str) -> None:
        """Replace the credential via the same atomic 0600 write path."""
        self.store_credential(credential)

    def status(self, hostname: Optional[str] = None) -> Dict[str, Any]:
        """Return safe identity metadata; never read or expose the credential."""
        agent_id = self.ensure_agent_id(hostname=hostname)
        data = self._read_identity()
        return {
            "agent_id": agent_id,
            "hostname": data.get("hostname", ""),
            "credential_configured": self.credential_path.is_file(),
        }

    def enroll(
        self,
        base_url: str,
        enrollment_token: str,
        hostname: str,
        *,
        os_name: Optional[str] = None,
        architecture: Optional[str] = None,
        config_version: str = "",
        machine_id: str = "",
        checks_offered: Optional[list[str]] = None,
        timeout: float = 10.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> Dict[str, Any]:
        """Enroll once and persist the returned agent UUID and credential."""
        agent_id = self.ensure_agent_id(hostname=hostname)
        payload = {
            "version": "1",
            "hostname": hostname,
            "os": os_name or os.name,
            "architecture": architecture or (os.uname().machine if hasattr(os, "uname") else "unknown"),
            "agent_version": __version__,
            "config_version": config_version,
            "machine_id": machine_id,
            "checks_offered": checks_offered or [],
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "nonce": secrets.token_urlsafe(18),
            "enrollment_token": enrollment_token,
            "signature": "",
        }
        request = urllib.request.Request(
            base_url.rstrip("/") + "/v1/agents/enroll",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = opener(request, timeout=timeout)
            with response as handle:
                status = int(getattr(handle, "status", getattr(handle, "code", 0)))
                body = handle.read(65537)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read(65537)
        except (urllib.error.URLError, OSError) as exc:
            raise IdentityError("enrollment request failed") from exc
        if len(body) > 65536:
            raise IdentityError("enrollment response exceeded size limit")
        try:
            result = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IdentityError("enrollment response was not valid JSON") from exc
        if status != 201 or not isinstance(result, dict):
            raise IdentityError(f"enrollment rejected with HTTP {status}")
        returned_id = result.get("agent_id")
        credential = result.get("auth_token")
        if not isinstance(returned_id, str) or not returned_id:
            raise IdentityError("enrollment response omitted agent_id")
        if not isinstance(credential, str) or not credential:
            raise IdentityError("enrollment response omitted credential")
        self._write_identity({"agent_id": returned_id, "hostname": hostname})
        self.store_credential(credential)
        safe = dict(result)
        safe.pop("auth_token", None)
        safe["credential_configured"] = True
        return safe

    def _read_identity(self) -> Dict[str, Any]:
        try:
            info = os.lstat(self.identity_path)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise IdentityError("identity file must be a regular file")
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise IdentityError("identity file must have mode 0600")
            with self.identity_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            raise IdentityError("identity file is invalid") from exc
        if not isinstance(data, dict):
            raise IdentityError("identity file must contain an object")
        return data

    def _write_identity(self, data: Dict[str, Any]) -> None:
        parent = self.identity_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(parent, 0o700)
        fd, temporary = tempfile.mkstemp(prefix=".agentpulse-identity-", dir=str(parent))
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = -1
                json.dump(data, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.identity_path)
            os.chmod(self.identity_path, 0o600)
        except Exception:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise


__all__ = ["IdentityError", "IdentityManager"]
