"""Agent check-in payload generation.

This module builds the JSON payload the agent will eventually send to the
AgentPulse backend. For now, it is intentionally dry-run friendly: build the
payload, print it, and do not require a network service.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import __version__
from .config import Config
from .runner import CycleSummary


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp with a Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def status_from_summary(summary: CycleSummary) -> str:
    """Map a cycle summary into a compact agent status."""
    if summary.errors:
        return "error"
    if summary.escalations or summary.blocked or summary.breaches:
        return "attention"
    return "ok"


def build_checkin_payload(
    cfg: Config,
    summary: CycleSummary,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the agent check-in payload from config + latest cycle summary."""
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
    """Serialize a check-in payload for CLI output."""
    return json.dumps(payload, indent=2, sort_keys=True)


class CheckinDeliveryError(RuntimeError):
    """Raised when check-in delivery fails safely."""


def send_checkin_payload(cfg: Config, payload: Dict[str, Any], opener=None) -> int:
    """POST a check-in payload to the configured endpoint.

    Uses urllib from the standard library to keep the agent dependency-free.
    Returns the HTTP status code on success.
    """
    if not cfg.checkin.endpoint_url:
        raise CheckinDeliveryError("checkin.endpoint_url is required for delivery")

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"AgentPulse/{__version__}",
    }
    if cfg.checkin.auth_token:
        headers["Authorization"] = f"Bearer {cfg.checkin.auth_token}"

    req = urllib.request.Request(
        cfg.checkin.endpoint_url,
        data=body,
        headers=headers,
        method="POST",
    )

    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=cfg.checkin.timeout_seconds) as resp:  # noqa: S310
            status = getattr(resp, "status", 200)
            if not 200 <= status < 300:
                raise CheckinDeliveryError(f"check-in endpoint returned HTTP {status}")
            return int(status)
    except (urllib.error.URLError, OSError) as exc:
        raise CheckinDeliveryError(f"check-in delivery failed: {exc}") from exc
