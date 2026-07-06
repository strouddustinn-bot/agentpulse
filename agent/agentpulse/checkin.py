"""Agent check-in payload generation.

This module builds the JSON payload the agent will eventually send to the
AgentPulse backend. For now, it is intentionally dry-run friendly: build the
payload, print it, and do not require a network service.
"""

from __future__ import annotations

import json
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
