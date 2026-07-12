"""The remediation decision loop.

Every auto-fix flows through a full cycle:

    Reason   -> _expected_state(): state the expected post-fix outcome
    Simulate -> dry-run the action, capture the predicted effect
    Gate     -> safety_gate(): executable safety predicates
    Act      -> run the validated action for real
    Verify   -> re-measure; escalate if the condition did not clear
    Record   -> capture the cycle for future analysis

The loop refuses to spiral: a fix that doesn't verify escalates to a human
instead of being blindly retried.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import remediation
from .models import Decision
from .remediation import RemediationResult

VerifyFn = Callable[[Decision], bool]

# Actions that may be green-lit for real execution. Default-deny: a new action
# must be deliberately reviewed and added here before the loop will ever run it.
_EXECUTABLE_ACTIONS = frozenset({
    "disk_cleanup",
    "service_restart",
    "process_kill",
    "ssh_block",
})


@dataclass
class CycleRecord:
    decision: Decision
    expectation: str = ""
    simulation: Optional[RemediationResult] = None
    gate_allowed: bool = False
    gate_reasons: List[str] = field(default_factory=list)
    execution: Optional[RemediationResult] = None
    verified: Optional[bool] = None
    outcome: str = "pending"
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "action": self.decision.action,
            "target": self.decision.target,
            "expectation": self.expectation,
            "gate_allowed": self.gate_allowed,
            "gate_reasons": self.gate_reasons,
            "simulated": bool(self.simulation),
            "executed": bool(self.execution and self.execution.performed),
            "verified": self.verified,
            "outcome": self.outcome,
            "notes": list(self.notes),
        }


def _expected_state(decision: Decision) -> str:
    if decision.action == "disk_cleanup":
        return f"expect disk usage on {decision.target} to drop below threshold after removing old files"
    if decision.action == "service_restart":
        return f"expect service {decision.target} to be 'active' after restart"
    if decision.action == "process_kill":
        obs = decision.observation
        name = obs.metadata.get("name", decision.target) if obs else decision.target
        return f"expect process {name} to be absent from /proc after kill + grace period"
    if decision.action == "ssh_block":
        return f"expect IP {decision.target} to be blocked in iptables INPUT chain"
    return f"expect {decision.target} condition to clear"


def safety_gate(decision: Decision, simulation: RemediationResult) -> "tuple[bool, List[str]]":
    """Gate: deny unless every safety predicate passes. Fail-closed."""
    reasons: List[str] = []

    # Rule 1: never act without a successful simulation.
    if simulation is None or not simulation.ok:
        err = simulation.error if simulation else "no simulation"
        reasons.append(f"no successful dry-run simulation ({err}); refusing to execute blind")
        return False, reasons

    # Rule 2: default-deny for unrecognised or alert-only actions.
    if decision.action not in _EXECUTABLE_ACTIONS:
        reasons.append(
            f"action {decision.action!r} is not in the executable allowlist; refusing to execute"
        )
        return False, reasons

    # Rule 3: process_kill requires kill_eligible flag from the check.
    if decision.action == "process_kill":
        obs = decision.observation
        meta = obs.metadata if obs else {}
        if not meta.get("kill_eligible", False):
            reasons.append(
                "process is not kill-eligible "
                "(not in kill_allowed_names or in never_kill list); "
                "refusing to kill"
            )
            return False, reasons
        pid = meta.get("pid")
        if not pid or int(pid) <= 1:
            reasons.append("invalid or missing PID; refusing to kill")
            return False, reasons

    # Rule 4: ssh_block requires a valid non-empty IP in the observation.
    if decision.action == "ssh_block":
        obs = decision.observation
        meta = obs.metadata if obs else {}
        ip = meta.get("ip") or decision.target
        if not ip or ip in ("0.0.0.0", "::", "127.0.0.1", "::1"):
        	reasons.append(f"refusing to block IP {ip!r}: loopback or empty address")
        	return False, reasons

    reasons.append("all safety predicates satisfied")
    return True, reasons


def run_cycle(
    decision: Decision,
    *,
    verify_fn: Optional[VerifyFn] = None,
    run_fn=None,
    force_dry_run: bool = False,
) -> CycleRecord:
    rec = CycleRecord(decision=decision)

    rec.expectation = _expected_state(decision)
    rec.simulation = remediation.execute(decision, dry_run=True, run_fn=run_fn)
    rec.gate_allowed, rec.gate_reasons = safety_gate(decision, rec.simulation)

    if not rec.gate_allowed:
        rec.outcome = "blocked"
        rec.notes.append("blocked by safety gate before execution")
        return rec

    if force_dry_run:
        rec.outcome = "simulated_only"
        rec.notes.append("dry-run only; no changes made")
        return rec

    rec.execution = remediation.execute(decision, dry_run=False, run_fn=run_fn)
    if not rec.execution.ok:
        rec.outcome = "failed"
        rec.notes.append(f"execution failed: {rec.execution.error}")
        return rec

    if not rec.execution.performed:
        rec.verified = False
        rec.outcome = "escalated"
        rec.notes.append(
            "action completed without changing anything; "
            "the breach cannot have been resolved — escalating to a human"
        )
        return rec

    if verify_fn is not None:
        rec.verified = bool(verify_fn(decision))
        if rec.verified:
            rec.outcome = "succeeded"
        else:
            rec.outcome = "escalated"
            rec.notes.append(
                "post-action verification did NOT clear the condition; "
                "escalating to a human instead of retrying"
            )
    else:
        rec.outcome = "executed_unverified"

    return rec
