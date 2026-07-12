"""Policy engine: turn an Observation + configured mode into a Decision.

This is the safety-critical core, written as pure functions so it is fully
unit-testable with no side effects.

Modes:
    off   -> ignore entirely (no decision)
    alert -> notify only, never act
    ask   -> queue for explicit human approval, never act automatically
    auto  -> act automatically now

Hard safety rules (cannot be overridden by config):
    * A process is NEVER killed automatically in v1. 'auto' on the process
      check is clamped down to 'ask'. The agent flags runaway processes; a
      human decides.
"""

from __future__ import annotations

from typing import Optional

from .models import Decision, Observation

# Maps a check type to the remediation action it can produce.
ACTION_FOR_CHECK = {
    "disk": "disk_cleanup",
    "service": "service_restart",
    "process": "process_alert",
}


def decide(check: str, mode: str, obs: Observation) -> Optional[Decision]:
    """Return a Decision for a breached observation, or None to do nothing.

    Only breached observations produce decisions. 'off' mode always yields None.
    """
    if not obs.breached:
        return None
    if mode == "off":
        return None

    action = ACTION_FOR_CHECK.get(check, "none")
    effective = mode
    clamped_from = None

    # Safety clamp: never auto-kill / auto-touch a process in v1.
    if check == "process" and mode == "auto":
        effective = "ask"
        clamped_from = "auto"

    if effective == "alert":
        return Decision(
            action=action,
            target=obs.target,
            mode_effective="alert",
            execute=False,
            requires_approval=False,
            reason=f"alert-only: {obs.detail}",
            clamped_from=clamped_from,
            observation=obs,
        )

    if effective == "ask":
        reason = f"ask-first: {obs.detail}"
        if clamped_from:
            reason += " (auto clamped to ask-first for safety: processes are never auto-killed in v1)"
        return Decision(
            action=action,
            target=obs.target,
            mode_effective="ask",
            execute=False,
            requires_approval=True,
            reason=reason,
            clamped_from=clamped_from,
            observation=obs,
        )

    # effective == "auto"
    return Decision(
        action=action,
        target=obs.target,
        mode_effective="auto",
        execute=True,
        requires_approval=False,
        reason=f"auto-fix: {obs.detail}",
        clamped_from=clamped_from,
        observation=obs,
    )
