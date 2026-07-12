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

# Alert deduplication: re-alert only after this many seconds of the same condition.
_DEFAULT_ALERT_COOLDOWN = 300  # 5 minutes


def mode_for(cfg: Config, check: str) -> str:
    return {
        "disk": cfg.disk.mode,
        "service": cfg.service.mode,
        "process": cfg.process.mode,
        "ssh": cfg.ssh.mode,
    }.get(check, "off")


def make_verify(cfg: Config, state: State = None, run_fn=None):
    """Build the verify step: re-measure after acting."""

    def verify(decision: Decision) -> bool:
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

        if decision.action == "process_kill":
            obs = decision.observation
            pid = obs.metadata.get("pid") if obs else None
            if not pid:
                return False
            # Verify the process is gone.
            from .remediation import _read_proc_name
            return _read_proc_name(int(pid)) is None

        if decision.action == "ssh_block":
            # Verify the iptables rule exists.
            from .remediation import _iptables_bin, _IPTABLES_BLOCK_CHAIN
            from .checks import _default_run
            rf = run_fn or _default_run
            ipt = _iptables_bin()
            if not ipt:
                return False
            obs = decision.observation
            ip = (obs.metadata.get("ip") if obs else None) or decision.target
            rc, _ = rf([ipt, "-C", _IPTABLES_BLOCK_CHAIN, "-s", ip, "-j", "DROP"])
            return rc == 0

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


def _push_to_hub(cfg: Config, state: State) -> None:
    """Push local state snapshot to the federation hub (best-effort)."""
    if not cfg.federation.enabled:
        return
    if cfg.federation.mode not in ("spoke", "both"):
        return
    hub_url = cfg.federation.hub_url
    if not hub_url:
        return
    import json
    import urllib.request
    import urllib.error
    hostname = cfg.resolved_hostname()
    payload = json.dumps({
        "agent_id": hostname,
        "hostname": hostname,
        "state": {
            "last_run": state.data.get("last_run"),
            "pending": list(state.data.get("pending", {}).values()),
            "history": state.data.get("history", [])[-10:],
            "blocked_ips": list(state.data.get("blocked_ips", {}).values()),
        },
    }).encode("utf-8")
    url = hub_url.rstrip("/") + "/fleet/heartbeat"
    secret = cfg.federation.secret
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except (urllib.error.URLError, OSError):
        pass  # hub push is best-effort; never crash the local agent


def run_once(
    cfg: Config,
    state: State,
    notifier: Notifier,
    dry_run: bool = False,
    gather_fn: Callable[[Config], List[Observation]] = checks.gather,
    run_fn=None,
) -> CycleSummary:
    summary = CycleSummary()

    # Expire stale IP blocks before checking.
    expired = state.expire_blocked_ips()
    for ip in expired:
        from .remediation import ssh_unblock
        ssh_unblock(ip, run_fn=run_fn)

    observations = gather_fn(cfg)
    summary.observations = len(observations)

    learn_baselines(cfg, state, observations, notifier, summary)

    for obs in observations:
        decision = policy.decide(obs.check, mode_for(cfg, obs.check), obs)
        if decision is None:
            continue
        summary.breaches += 1

        # Deduplication: skip re-alerting the same condition within cooldown window.
        cooldown_key = f"{obs.check}:{obs.target}"
        if decision.mode_effective == "alert" and not decision.requires_approval:
            if state.is_on_cooldown(cooldown_key):
                continue
            state.set_cooldown(cooldown_key)

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
            rec = decision_loop.run_cycle(
                decision,
                verify_fn=make_verify(cfg, state=state, run_fn=run_fn),
                run_fn=run_fn,
                force_dry_run=dry_run,
            )
            label = f"{decision.action}:{decision.target}"
            detail_src = rec.execution or rec.simulation
            details = "\n".join(
                [rec.expectation]
                + (detail_src.details if detail_src else [])
                + rec.notes
            )

            # Record to history.
            history_entry = rec.as_dict()
            history_entry["dry_run"] = dry_run
            history_entry["ts"] = time.time()
            state.record_history(history_entry)

            # Track blocked IPs in state.
            if rec.outcome in ("succeeded", "executed_unverified") and decision.action == "ssh_block":
                obs_meta = obs.metadata
                ip = obs_meta.get("ip") or decision.target
                dur = obs_meta.get("block_duration_seconds", 3600)
                state.block_ip(ip, int(dur), obs.detail)

            if rec.outcome in ("succeeded", "executed_unverified", "simulated_only"):
                summary.actions_taken.append(label)
                state.clear_cooldown(cooldown_key)
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
            else:
                err = rec.execution.error if rec.execution else "unknown error"
                summary.errors.append(f"{label}: {err}")
                notifier.send(f"auto-fix FAILED: {decision.action}", err or "unknown error")

        else:
            summary.alerts.append(f"{obs.check}:{obs.target}")
            notifier.send(f"alert: {obs.check}", obs.detail)

    state.mark_run()
    state.save()
    _push_to_hub(cfg, state)
    return summary


def approve(
    cfg: Config, state: State, pending_id: str, dry_run: bool = False, run_fn=None
) -> Optional[decision_loop.CycleRecord]:
    """Execute a previously queued ask-first action after human approval."""
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
        verify_fn=make_verify(cfg, state=state, run_fn=run_fn),
        run_fn=run_fn,
        force_dry_run=dry_run,
    )
    if not dry_run:
        history_entry = rec.as_dict()
        history_entry["approved"] = True
        history_entry["ts"] = time.time()
        state.record_history(history_entry)

        if rec.outcome in ("succeeded", "executed_unverified") and decision.action == "ssh_block":
            ip = obs.metadata.get("ip") or decision.target
            dur = obs.metadata.get("block_duration_seconds", 3600)
            state.block_ip(ip, int(dur), "approved block")

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


def run_loop(
    cfg: Config,
    state: State,
    notifier: Notifier,
    dry_run: bool = False,
    max_cycles: Optional[int] = None,
) -> None:  # pragma: no cover - long running
    from . import dashboard, federation

    # Start optional background servers.
    if cfg.dashboard.enabled:
        dashboard.start(cfg, state)
    if cfg.federation.enabled and cfg.federation.mode in ("hub", "both"):
        federation.start_hub(cfg, state)

    cycles = 0
    while True:
        run_once(cfg, state, notifier, dry_run=dry_run)
        cycles += 1
        print(f"[heartbeat] cycle {cycles} | {time.strftime('%H:%M:%S')}", flush=True)
        if max_cycles is not None and cycles >= max_cycles:
            return
        time.sleep(cfg.interval_seconds)
