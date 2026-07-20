"""The run loop: gather -> decide -> act / queue / alert -> notify -> persist."""

from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from . import baseline, checks, control_plane, decision_loop, policy
from .checkin import CheckinClient, CheckinDeliveryError, build_checkin_payload, send_checkin_payload
from .config import Config
from .models import Decision, Observation
from .retry import CredentialRecoveryRequired
from .spool import Spool, SpoolFull, SpoolPermanentFailure
from .state import State


class NotifierLike(Protocol):
    def send(self, title: str, body: str) -> bool: ...


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
    notifier: NotifierLike,
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


def send_backend_checkin(
    cfg: Config,
    summary: CycleSummary,
    notifier: NotifierLike,
    sender: Callable[[Config, Dict[str, Any]], int] = send_checkin_payload,
) -> bool:
    """Send a best-effort backend check-in if configured.

    Backend outages must never stop local monitoring/remediation. Failure is
    surfaced through the normal notifier and the next cycle will try again.
    """
    if not cfg.checkin.endpoint_url:
        return False
    payload = build_checkin_payload(cfg, summary)
    try:
        if sender is send_checkin_payload and cfg.checkin.credential_file:
            from .identity import IdentityManager
            from .spool import Spool
            spool = Spool(cfg.checkin.spool_directory)
            client = CheckinClient(
                IdentityManager(cfg.checkin.identity_file, cfg.checkin.credential_file),
                spool,
                endpoint_url=cfg.checkin.endpoint_url,
                timeout=cfg.checkin.timeout_seconds,
            )
            # Drain older durable events before the current heartbeat so outage
            # recovery preserves FIFO order and does not strand the spool.
            try:
                client.replay(max_events=2)
            except CredentialRecoveryRequired:
                # Preserve the current event behind the rejected backlog. A
                # credential-recovery signal must not create a telemetry gap.
                client.queue(payload)
                raise
            if spool.list_pending():
                client.queue(payload)
                return False
            status = client.send(payload)
            if status is None:
                notifier.send(
                    "backend check-in failed",
                    "event queued for retry",
                )
                return False
            return True
        else:
            sender(cfg, payload)
        return True
    except CredentialRecoveryRequired as exc:
        notifier.send("backend credential recovery required", str(exc))
        return False
    except (CheckinDeliveryError, SpoolFull, OSError) as exc:
        notifier.send("backend check-in failed", str(exc))
        return False


def send_control_plane_heartbeat(
    cfg: Config,
    state: State,
    summary: CycleSummary,
    notifier: NotifierLike,
) -> bool:
    """Contain telemetry spool failures so local monitoring always continues."""
    if not cfg.control_plane.enabled:
        return False
    try:
        return _send_control_plane_heartbeat(cfg, state, summary, notifier)
    except (OSError, SpoolFull, ValueError) as exc:
        notifier.send("control-plane heartbeat spool failed", str(exc))
        return False


def _send_control_plane_heartbeat(
    cfg: Config,
    state: State,
    summary: CycleSummary,
    notifier: NotifierLike,
) -> bool:
    """Push a bounded, best-effort SaaS heartbeat without affecting local safety."""
    if not cfg.control_plane.enabled:
        return False
    spool = Spool(cfg.control_plane.spool_directory)
    heartbeat_summary = {
        "observations": summary.observations,
        "breaches": summary.breaches,
        "errors": list(summary.errors),
    }

    def deliver(event: Dict[str, Any]) -> bool:
        if event.get("event_type") != "control_plane_heartbeat":
            return False
        result = control_plane.push_heartbeat_payload(
            cfg.control_plane.base_url,
            cfg.control_plane.credential_file,
            event["payload"],
            cfg.control_plane.timeout_seconds,
        )
        if result.status == 401:
            raise CredentialRecoveryRequired("control-plane credential rejected")
        if result.status in (400, 403, 404):
            notifier.send(
                "control-plane heartbeat rejected",
                f"HTTP {result.status}: {result.error}",
            )
            raise SpoolPermanentFailure(result.error or f"HTTP {result.status}")
        return result.ok

    cycle_id = uuid.uuid4().hex
    payload = control_plane.build_heartbeat_payload(
        state.data, heartbeat_summary, cycle_id
    )
    try:
        spool.replay(
            deliver,
            max_events=3,
            propagate_exceptions=(CredentialRecoveryRequired,),
        )
    except CredentialRecoveryRequired as exc:
        try:
            spool.enqueue(
                "control_plane_heartbeat", payload, event_id=cycle_id
            )
        except (SpoolFull, ValueError) as spool_exc:
            notifier.send("control-plane heartbeat spool failed", str(spool_exc))
        notifier.send("control-plane credential recovery required", str(exc))
        return False
    if spool.list_pending():
        try:
            spool.enqueue(
                "control_plane_heartbeat", payload, event_id=cycle_id
            )
        except (SpoolFull, ValueError) as exc:
            notifier.send("control-plane heartbeat spool failed", str(exc))
        return False
    result = control_plane.push_heartbeat_payload(
        cfg.control_plane.base_url,
        cfg.control_plane.credential_file,
        payload,
        cfg.control_plane.timeout_seconds,
    )
    if not result.ok:
        if result.status == 401:
            notifier.send(
                "control-plane credential recovery required",
                "control-plane credential rejected",
            )
            return False
        if result.status in (400, 403, 404):
            notifier.send(
                "control-plane heartbeat rejected",
                f"HTTP {result.status}: {result.error}",
            )
            return False
        try:
            spool.enqueue(
                "control_plane_heartbeat", payload, event_id=cycle_id
            )
        except (SpoolFull, ValueError) as exc:
            notifier.send("control-plane heartbeat spool failed", str(exc))
        notifier.send("control-plane heartbeat failed", result.error)
    return result.ok


def run_once(
    cfg: Config,
    state: State,
    notifier: NotifierLike,
    dry_run: bool = False,
    gather_fn: Callable[[Config], List[Observation]] = checks.gather,
    run_fn=None,
    checkin_sender: Callable[[Config, Dict[str, Any]], int] = send_checkin_payload,
) -> CycleSummary:
    if dry_run:
        # Preview against an isolated snapshot. Dry-run must not change pending
        # approvals, baselines, history, last-run bookkeeping, or the state file.
        state = copy.deepcopy(state)
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
                + (
                    rec.execution.details
                    if rec.execution
                    else (rec.simulation.details if rec.simulation else [])
                )
                + rec.notes
            )
            history_entry = rec.as_dict()
            history_entry["dry_run"] = dry_run
            history_entry["ts"] = time.time()
            state.record_history(history_entry)
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
                    details
                    + "\n→ needs a human; the agent will not retry automatically.",
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
                notifier.send(
                    f"auto-fix FAILED: {decision.action}", err or "unknown error"
                )
        else:
            summary.alerts.append(f"{obs.check}:{obs.target}")
            notifier.send(f"alert: {obs.check}", obs.detail)

    if not dry_run:
        state.mark_run()
        state.save()
        send_backend_checkin(cfg, summary, notifier, sender=checkin_sender)
        send_control_plane_heartbeat(cfg, state, summary, notifier)
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
        history_entry = rec.as_dict()
        history_entry["approved"] = True
        history_entry["ts"] = time.time()
        state.record_history(history_entry)
        state.save()
    return rec


def deny(state: State, pending_id: str) -> Optional[dict]:
    """Reject a queued ask-first action and preserve an audit record."""
    entry = state.pop_pending(pending_id)
    if entry is None:
        return None
    state.record_history(
        {
            "action": entry.get("action"),
            "target": entry.get("target"),
            "outcome": "denied",
            "reason": "denied by operator",
            "ts": time.time(),
        }
    )
    state.save()
    return entry


def run_loop(
    cfg: Config,
    state: State,
    notifier: NotifierLike,
    dry_run: bool = False,
    max_cycles: Optional[int] = None,
) -> None:  # pragma: no cover - long running
    cycles = 0
    while True:
        run_once(cfg, state, notifier, dry_run=dry_run)
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return
        time.sleep(cfg.interval_seconds)
