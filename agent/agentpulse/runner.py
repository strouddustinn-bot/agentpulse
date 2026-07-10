"""The run loop: gather -> decide -> act / queue / alert -> notify -> persist."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import baseline, checks, decision_loop, policy, remediation
from .config import Config
from .models import Decision, Observation
from .notify import Notifier
from .state import State


def mode_for(cfg: Config, check: str) -> str:
    return {
        "disk": cfg.disk.mode,
        "service": cfg.service.mode,
        "process": cfg.process.mode,
    }.get(check, "off")


def make_verify(cfg: Config, run_fn=None):
    """Build the verify step: re-measure after acting."""

    def verify(decision: Decision) -> bool:
        # Verification must be a positive re-measurement of the target. If we
        # can't find the target in a fresh check (empty list, renamed mount,
        # transient check failure), we do NOT claim the condition cleared —
        # returning False routes the cycle to escalation instead of a false
        # all-clear.
        if decision.action == "disk_cleanup":
            for obs in checks.check_disk(cfg.disk):
                if obs.target == decision.target:
                    return not obs.breached
            return False
        if decision.action == "service_restart":
            svc_cfg = cfg.service
            obs_list = (
                checks.check_services(svc_cfg, run_fn=run_fn)
                if run_fn
                else checks.check_services(svc_cfg)
            )
            for obs in obs_list:
                if obs.target == decision.target:
                    return not obs.breached
            return False
        return False

    return verify


@dataclass
class CycleSummary:
    observations: int = 0
    breaches: int = 0
    actions_taken: List[str] = field(default_factory=list)
    queued: List[str] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)
    anomalies: List[str] = field(default_factory=list)
    escalations: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def learn_baselines(
    cfg: Config,
    state: State,
    observations: List[Observation],
    notifier: Notifier,
    summary: "CycleSummary",
    mem_fn=checks.host_memory_percent,
) -> None:
    """Recall pillar: update per-metric baselines and raise advisory anomaly
    alerts. Never triggers remediation."""
    if not cfg.baseline.enabled:
        return
    samples = {}
    for obs in observations:
        if obs.check == "disk":
            samples[f"disk:{obs.target}"] = obs.value
    mem = mem_fn()
    if mem is not None:
        samples["mem"] = mem
    for key, value in samples.items():
        anomalous, reason = baseline.observe(state.baselines, key, value, cfg.baseline)
        if anomalous:
            summary.anomalies.append(key)
            notifier.send(f"baseline anomaly: {key}", reason)


def run_once(
    cfg: Config,
    state: State,
    notifier: Notifier,
    dry_run: bool = False,
    gather_fn: Callable[[Config], List[Observation]] = checks.gather,
    run_fn=None,
) -> CycleSummary:
    summary = CycleSummary()
    observations = gather_fn(cfg)
    summary.observations = len(observations)

    # Recall pillar: learn normal + flag anomalies (advisory, before remediation).
    learn_baselines(cfg, state, observations, notifier, summary)

    for obs in observations:
        decision = policy.decide(obs.check, mode_for(cfg, obs.check), obs)
        if decision is None:
            continue
        summary.breaches += 1

        if decision.requires_approval:
            if not state.has_pending(decision):
                pid = state.queue_pending(decision)
                notifier.send(
                    f"approval needed: {decision.action}",
                    f"id {pid} — {decision.reason}\n"
                    f"approve with: agentpulse approve <config> {pid}",
                )
            summary.queued.append(f"{decision.action}:{decision.target}")
        elif decision.execute:
            # Run the full decision loop: simulate -> validate -> execute ->
            # verify -> record. Never a blind destructive action.
            rec = decision_loop.run_cycle(
                decision,
                verify_fn=make_verify(cfg, run_fn=run_fn),
                run_fn=run_fn,
                force_dry_run=dry_run,
            )
            label = f"{decision.action}:{decision.target}"
            details = "\n".join(
                [rec.expectation]
                + (rec.execution.details if rec.execution else (rec.simulation.details if rec.simulation else []))
                + rec.notes
            )
            if rec.outcome in ("succeeded", "executed_unverified", "simulated_only"):
                summary.actions_taken.append(label)
                notifier.send(
                    f"{'(dry-run) ' if dry_run else ''}decision loop {rec.outcome}: {decision.action}",
                    details,
                )
            elif rec.outcome == "escalated":
                summary.escalations.append(label)
                notifier.send(
                    f"ESCALATION: {decision.action} ran but did not clear",
                    details + "\n→ needs a human; the agent will not retry automatically.",
                )
            elif rec.outcome == "blocked":
                summary.blocked.append(label)
                notifier.send(
                    f"safety gate blocked: {decision.action}",
                    "; ".join(rec.gate_reasons),
                )
            else:  # failed
                err = rec.execution.error if rec.execution else "unknown error"
                summary.errors.append(f"{label}: {err}")
                notifier.send(f"auto-fix FAILED: {decision.action}", err or "unknown error")
        else:
            summary.alerts.append(f"{obs.check}:{obs.target}")
            notifier.send(f"alert: {obs.check}", obs.detail)

    state.mark_run()
    state.save()
    return summary


def approve(
    cfg: Config, state: State, pending_id: str, dry_run: bool = False, run_fn=None
) -> Optional[decision_loop.CycleRecord]:
    """Execute a previously queued ask-first action after human approval.

    Approved actions run the SAME full decision loop as auto actions —
    simulate -> gate -> act -> verify -> record — so human approval never
    bypasses the safety gate or the verify-or-escalate guarantee. Conditions
    can change between queueing and approval; the gate re-validates against the
    freshly simulated plan rather than trusting the original queued decision.

    A dry-run approval is a preview: it peeks at the pending entry without
    consuming it, so a later real approval can still act on it. Only a real
    approval removes the entry from the queue.
    """
    entry = state.get_pending(pending_id) if dry_run else state.pop_pending(pending_id)
    if entry is None:
        return None
    obs = Observation(
        check=entry.get("check", ""),
        target=entry["target"],
        breached=True,
        metadata=entry.get("metadata", {}),
    )
    decision = Decision(
        action=entry["action"],
        target=entry["target"],
        mode_effective="approved",
        execute=True,
        requires_approval=False,
        reason="approved by operator",
        observation=obs,
    )
    rec = decision_loop.run_cycle(
        decision,
        verify_fn=make_verify(cfg, run_fn=run_fn),
        run_fn=run_fn,
        force_dry_run=dry_run,
    )
    if not dry_run:
        # Only a real approval mutates the queue; a dry-run preview leaves it intact.
        state.save()
    return rec


def deny(state: State, pending_id: str) -> Optional[dict]:
    """Reject a previously queued ask-first action without executing it."""
    entry = state.pop_pending(pending_id)
    if entry is None:
        return None
    state.record_history({
        "action": entry.get("action"),
        "target": entry.get("target"),
        "outcome": "denied",
        "reason": "denied by operator",
        "ts": time.time(),
    })
    state.save()
    return entry


def run_loop(cfg: Config, state: State, notifier: Notifier, dry_run: bool = False, max_cycles: Optional[int] = None) -> None:  # pragma: no cover - long running
    cycles = 0
    while True:
        run_once(cfg, state, notifier, dry_run=dry_run)
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return
        time.sleep(cfg.interval_seconds)
