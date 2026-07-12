"""Policy engine: turn an Observation + configured mode into a Decision.

Pure functions, fully unit-testable.

Modes:
    off   -> ignore entirely (no decision)
    alert -> notify only, never act
    ask   -> queue for explicit human approval
    auto  -> act automatically

Process kill is allowed in auto mode but gated by a per-name allowlist and
hard safety invariants in the decision loop (never kill PID 1, own process,
or names on the never_kill list). The clamp that forced process auto→ask has
been removed — auto now means auto, subject to those gates.
"""

from __future__ import annotations

from typing import Optional

from .models import Decision, Observation

# Maps a check type to the remediation action it can produce in auto mode.
# In alert/ask mode the action is informational only (execute=False).
ACTION_FOR_CHECK = {
    "disk": "disk_cleanup",
    "service": "service_restart",
    "process": "process_kill",
    "ssh": "ssh_block",
}

# Alert-only action names used when mode != auto (no remediation, just info).
ALERT_ACTION_FOR_CHECK = {
    "disk": "disk_cleanup",
    "service": "service_restart",
    "process": "process_alert",
    "ssh": "ssh_alert",
}


def decide(check: str, mode: str, obs: Observation) -> Optional[Decision]:
    """Return a Decision for a breached observation, or None to do nothing."""
    if not obs.breached:
        return None
    if mode == "off":
        return None

    auto_action = ACTION_FOR_CHECK.get(check, "none")
    alert_action = ALERT_ACTION_FOR_CHECK.get(check, "none")

    if mode == "alert":
        return Decision(
            action=alert_action,
            target=obs.target,
            mode_effective="alert",
            execute=False,
            requires_approval=False,
            reason=f"alert-only: {obs.detail}",
            observation=obs,
        )

    if mode == "ask":
        return Decision(
            action=auto_action,
            target=obs.target,
            mode_effective="ask",
            execute=False,
            requires_approval=True,
            reason=f"ask-first: {obs.detail}",
            observation=obs,
        )

    # mode == "auto"
    return Decision(
        action=auto_action,
        target=obs.target,
        mode_effective="auto",
        execute=True,
        requires_approval=False,
        reason=f"auto-fix: {obs.detail}",
        observation=obs,
    )
