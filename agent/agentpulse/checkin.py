"""Authenticated check-in payloads with retry and durable offline spooling."""
from __future__ import annotations

import json
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from . import __version__
from .config import Config
from .identity import IdentityManager
from .redaction import redact
from .retry import CredentialRecoveryRequired, RetryBudgetExhausted, RetryPolicy
from .spool import Spool

if TYPE_CHECKING:
    from .runner import CycleSummary


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def status_from_summary(summary: "CycleSummary") -> str:
    if summary.errors:
        return "error"
    if summary.escalations or summary.blocked or summary.breaches:
        return "attention"
    return "ok"


def build_checkin_payload(cfg: Config, summary: "CycleSummary", timestamp: Optional[str] = None) -> Dict[str, Any]:
    return {
        "agent_id": cfg.resolved_hostname(),
        "hostname": cfg.resolved_hostname(),
        "status": status_from_summary(summary),
        "observations": summary.observations,
        "breaches": summary.breaches,
        "actions": len(summary.actions_taken),
        "queued": len(summary.queued),
        "alerts": len(summary.alerts),
        "anomalies": len(summary.anomalies),
        "escalations": len(summary.escalations),
        "blocked": len(summary.blocked),
        "errors": len(summary.errors),
        "timestamp": timestamp or utc_now_iso(),
        "version": __version__,
    }


def payload_to_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


class CheckinDeliveryError(RuntimeError):
    """Check-in failed and was not acknowledged."""


class CheckinHTTPError(CheckinDeliveryError):
    def __init__(self, status: int, message: str = "") -> None:
        self.status = status
        self.headers: Dict[str, Any] = {}
        super().__init__(message or f"check-in endpoint returned HTTP {status}")


class CheckinClient:
    def __init__(self, identity: IdentityManager, spool: Spool, *, endpoint_url: str = "http://localhost:8088", timeout: float = 10.0, opener: Optional[Callable[..., Any]] = None, retry: Optional[RetryPolicy] = None, audit: Any = None) -> None:
        self.identity = identity
        self.spool = spool
        self.endpoint_url = endpoint_url.rstrip("/")
        self.timeout = timeout
        self.opener = opener or urllib.request.urlopen
        self.retry = retry or RetryPolicy()
        self.audit = audit

    def send(self, payload: Dict[str, Any], *, event_id: Optional[str] = None) -> Optional[int]:
        safe = redact(dict(payload))
        safe["agent_id"] = self.identity.ensure_agent_id()
        event_id = event_id or uuid.uuid4().hex
        try:
            status = self._deliver(safe, event_id=event_id)
            self._record_audit("checkin.acknowledged", event_id, {"status": status})
            return status
        except CheckinHTTPError as exc:
            if exc.status == 401:
                raise CredentialRecoveryRequired("check-in credential rejected") from exc
            if exc.status in (400, 403, 404):
                raise
            self.spool.enqueue("check_in", safe, event_id=event_id)
            self._record_audit("checkin.spooled", event_id, {"reason": "http_transient_failure"})
            return None
        except (OSError, urllib.error.URLError, CheckinDeliveryError, RetryBudgetExhausted) as exc:
            if isinstance(exc, CredentialRecoveryRequired):
                raise
            self.spool.enqueue("check_in", safe, event_id=event_id)
            self._record_audit("checkin.spooled", event_id, {"reason": "network_failure"})
            return None

    def replay(self) -> int:
        def acknowledge(event: Dict[str, Any]) -> bool:
            try:
                self._deliver(event["payload"], event_id=event["event_id"])
                self._record_audit("checkin.replayed", event["event_id"], {"acknowledged": True})
                return True
            except CredentialRecoveryRequired:
                raise
            except (OSError, urllib.error.URLError, CheckinDeliveryError, RetryBudgetExhausted):
                return False
        return self.spool.replay(acknowledge)

    def _record_audit(self, event_type: str, event_id: str, result: Dict[str, Any]) -> None:
        if self.audit is not None:
            self.audit.append(
                agent_id=self.identity.ensure_agent_id(), event_type=event_type,
                correlation_id=event_id, actor="agent", reason="check-in lifecycle",
                policy={}, evidence_before={}, action={}, result=result,
                evidence_after={}, agent_version=__version__, config_version="",
            )

    def _deliver(self, payload: Dict[str, Any], *, event_id: Optional[str]) -> int:
        def operation() -> int:
            body = json.dumps(redact(payload), separators=(",", ":")).encode()
            headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": f"AgentPulse/{__version__}", "Authorization": f"Bearer {self.identity.read_credential()}"}
            if event_id:
                headers["X-Idempotency-Key"] = event_id
            req = urllib.request.Request(self.endpoint_url + "/v1/agents/check-in", data=body, headers=headers, method="POST")
            try:
                with self.opener(req, timeout=self.timeout) as response:
                    status = int(getattr(response, "status", getattr(response, "code", 200)))
            except urllib.error.HTTPError as exc:
                error = CheckinHTTPError(exc.code, "check-in rejected")
                error.headers = dict(exc.headers or {})
                raise error
            if not 200 <= status < 300:
                raise CheckinHTTPError(status)
            return status
        return int(self.retry.run(operation))


def send_checkin_payload(cfg: Config, payload: Dict[str, Any], opener=None) -> int:
    if not cfg.checkin.endpoint_url:
        raise CheckinDeliveryError("checkin.endpoint_url is required for delivery")
    body = json.dumps(redact(payload)).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": f"AgentPulse/{__version__}"}
    if cfg.checkin.auth_token:
        headers["Authorization"] = f"Bearer {cfg.checkin.auth_token}"
    req = urllib.request.Request(cfg.checkin.endpoint_url, data=body, headers=headers, method="POST")
    try:
        with (opener or urllib.request.urlopen)(req, timeout=cfg.checkin.timeout_seconds) as resp:
            status = getattr(resp, "status", 200)
            if not 200 <= status < 300:
                raise CheckinDeliveryError(f"check-in endpoint returned HTTP {status}")
            return int(status)
    except (urllib.error.URLError, OSError) as exc:
        raise CheckinDeliveryError(f"check-in delivery failed: {exc}") from exc


__all__ = ["CheckinClient", "CheckinDeliveryError", "CheckinHTTPError", "build_checkin_payload", "payload_to_json", "send_checkin_payload", "status_from_summary"]

if __name__ == "__main__":
    raise SystemExit("library module")

# Exported for callers that need to distinguish recovery from transient outage.
_ = CredentialRecoveryRequired
