"""The Ouroboros remediation cycle.

Adapts the Sovereign-Ouroboros-OS loop
(Imagine -> Simulate -> Validate -> Execute/Evolve -> Expand, the loop that eats
its own tail) to autonomous server remediation. Every auto-fix flows through the
full cycle so the agent never takes a destructive action it hasn't first
simulated, ethically validated, and then verified.

Pillar mapping:
    NeuroSynth    (Imagine)        -> _imagine(): expected post-fix state
    ChronoWeave   (Simulate)       -> dry-run the action, capture predicted effect
    EthosCompiler (Validate)       -> ethos_gate(): executable safety predicates
    MetaMorph     (Execute/Evolve) -> run the validated action for real
    <tail>        (Verify)         -> re-measure; escalate if it did not clear
    HiveMind      (Expand)         -> record the cycle for future federation
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
    """A full Ouroboros pass over one remediation Decision."""

    decision: Decision
    expectation: str = ""
    simulation: Optional[RemediationResult] = None
    ethics_allowed: bool = False
    ethics_reasons: List[str] = field(default_factory=list)
    execution: Optional[RemediationResult] = None
    verified: Optional[bool] = None
    outcome: str = "pending"  # blocked|simulated_only|failed|escalated|succeeded|executed_unverified
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "action": self.decision.action,
            "target": self.decision.target,
            "expectation": self.expectation,
            "ethics_allowed": self.ethics_allowed,
            "ethics_reasons": self.ethics_reasons,
            "simulated": bool(self.simulation),
            "executed": bool(self.execution and self.execution.performed),
            "verified": self.verified,
            "outcome": self.outcome,
            "notes": list(self.notes),
        }


def _imagine(decision: Decision) -> str:
    """NeuroSynth: state the expected outcome before acting."""
    if decision.action == "disk_cleanup":
        return f"expect disk usage on {decision.target} to drop below its threshold after removing old files"
    if decision.action == "service_restart":
        return f"expect service {decision.target} to be 'active' after restart"
    return f"expect {decision.target} condition to clear"


def ethos_gate(decision: Decision, simulation: RemediationResult) -> "tuple[bool, List[str]]":
    """EthosCompiler: executable safety predicates. Deny unless every rule passes.

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

    reasons.append("all ethos predicates satisfied")
    return True, reasons


def run_cycle(
    decision: Decision,
    *,
    verify_fn: Optional[VerifyFn] = None,
    run_fn=None,
    force_dry_run: bool = False,
) -> CycleRecord:
    rec = CycleRecord(decision=decision)

    # 1. NeuroSynth — imagine the intended end-state.
    rec.expectation = _imagine(decision)

    # 2. ChronoWeave — simulate via dry-run before any real change.
    rec.simulation = remediation.execute(decision, dry_run=True, run_fn=run_fn)

    # 3. EthosCompiler — validate against executable safety predicates.
    rec.ethics_allowed, rec.ethics_reasons = ethos_gate(decision, rec.simulation)
    if not rec.ethics_allowed:
        rec.outcome = "blocked"
        rec.notes.append("blocked by ethos gate before execution")
        return rec

    if force_dry_run:
        rec.outcome = "simulated_only"
        rec.notes.append("dry-run only; no changes made")
        return rec

    # 4. MetaMorph — execute the validated action for real.
    rec.execution = remediation.execute(decision, dry_run=False, run_fn=run_fn)
    if not rec.execution.ok:
        rec.outcome = "failed"
        rec.notes.append(f"execution failed: {rec.execution.error}")
        return rec

    # 5. Tail — verify the condition actually cleared. Never blind-retry.
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

    # 6. HiveMind — the record itself is the unit of future federation.
    return rec
