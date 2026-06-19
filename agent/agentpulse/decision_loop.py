"""The remediation decision loop.

Every auto-fix flows through a full cycle so the agent never takes a destructive
action it hasn't first simulated, validated against safety predicates, and then
verified:

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


@dataclass
class CycleRecord:
    """A full decision-loop pass over one remediation Decision."""

    decision: Decision
    expectation: str = ""
    simulation: Optional[RemediationResult] = None
    gate_allowed: bool = False
    gate_reasons: List[str] = field(default_factory=list)
    execution: Optional[RemediationResult] = None
    verified: Optional[bool] = None
    outcome: str = "pending"  # blocked|simulated_only|failed|escalated|succeeded|executed_unverified
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
    """Reason: state the expected outcome before acting."""
    if decision.action == "disk_cleanup":
        return f"expect disk usage on {decision.target} to drop below its threshold after removing old files"
    if decision.action == "service_restart":
        return f"expect service {decision.target} to be 'active' after restart"
    return f"expect {decision.target} condition to clear"


def safety_gate(decision: Decision, simulation: RemediationResult) -> "tuple[bool, List[str]]":
    """Gate: executable safety predicates. Deny unless every rule passes.

    These are hard, code-level invariants — not config the operator can relax.
    """
    reasons: List[str] = []

    # Rule 1: never act without a successful simulation.
    if simulation is None or not simulation.ok:
        reasons.append("no successful dry-run simulation; refusing to execute blind")
        return False, reasons

    # Rule 2: the process check never produces an executable action.
    if decision.action == "process_alert":
        reasons.append("process actions are alert-only and never executed automatically")
        return False, reasons

    # Rule 3: disk cleanup must have produced a bounded, simulated plan.
    if decision.action == "disk_cleanup" and simulation.error:
        reasons.append(f"cleanup simulation reported error: {simulation.error}")
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

    # 1. Reason — state the intended end-state.
    rec.expectation = _expected_state(decision)

    # 2. Simulate — dry-run before any real change.
    rec.simulation = remediation.execute(decision, dry_run=True, run_fn=run_fn)

    # 3. Gate — validate against executable safety predicates.
    rec.gate_allowed, rec.gate_reasons = safety_gate(decision, rec.simulation)
    if not rec.gate_allowed:
        rec.outcome = "blocked"
        rec.notes.append("blocked by safety gate before execution")
        return rec

    if force_dry_run:
        rec.outcome = "simulated_only"
        rec.notes.append("dry-run only; no changes made")
        return rec

    # 4. Act — execute the validated action for real.
    rec.execution = remediation.execute(decision, dry_run=False, run_fn=run_fn)
    if not rec.execution.ok:
        rec.outcome = "failed"
        rec.notes.append(f"execution failed: {rec.execution.error}")
        return rec

    # 5. Verify — confirm the condition actually cleared. Never blind-retry.
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

    # 6. Record — the cycle record is the unit of future analysis.
    return rec
