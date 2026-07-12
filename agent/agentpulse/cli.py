"""Command-line entrypoint for AgentPulse."""

from __future__ import annotations

import argparse
import sys
import time
from typing import List, Optional

from . import __version__, config as config_mod
from .notify import Notifier
from .runner import approve, deny, run_loop, run_once
from .state import State


def _load(config_path: str):
    cfg = config_mod.load(config_path)
    state = State.load(cfg.state_file)
    notifier = Notifier(cfg.notify)
    return cfg, state, notifier


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentpulse", description="AgentPulse monitoring + remediation agent")
    p.add_argument("--version", action="version", version=f"agentpulse {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    pv = sub.add_parser("validate", help="validate a config file")
    pv.add_argument("config")

    pr = sub.add_parser("run-once", help="run a single check/remediate cycle")
    pr.add_argument("config")
    pr.add_argument("--dry-run", action="store_true", help="never modify the system; report what would happen")

    pl = sub.add_parser("run", help="run continuously on the configured interval")
    pl.add_argument("config")
    pl.add_argument("--dry-run", action="store_true")
    pl.add_argument("--max-cycles", type=int, default=None, help="stop after N cycles (testing)")

    pp = sub.add_parser("list-pending", help="list ask-first actions awaiting approval")
    pp.add_argument("config")

    pa = sub.add_parser("approve", help="approve and execute a pending ask-first action")
    pa.add_argument("config")
    pa.add_argument("pending_id")
    pa.add_argument("--dry-run", action="store_true")

    pd = sub.add_parser("deny", help="reject a pending ask-first action without executing it")
    pd.add_argument("config")
    pd.add_argument("pending_id")

    ph = sub.add_parser("history", help="show recent agent action history")
    ph.add_argument("config")
    ph.add_argument("--limit", type=int, default=20, help="number of records to show")

    pu = sub.add_parser("unblock-ip", help="remove an iptables block for an IP address")
    pu.add_argument("config")
    pu.add_argument("ip")
    pu.add_argument("--dry-run", action="store_true")

    pbi = sub.add_parser("list-blocked", help="list currently blocked IP addresses")
    pbi.add_argument("config")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "validate":
        try:
            config_mod.load(args.config)
        except config_mod.ConfigError as exc:
            print(f"INVALID: {exc}", file=sys.stderr)
            return 2
        print("OK: config is valid")
        return 0

    if args.command == "run-once":
        cfg, state, notifier = _load(args.config)
        summary = run_once(cfg, state, notifier, dry_run=args.dry_run)
        print(
            f"observations={summary.observations} breaches={summary.breaches} "
            f"actions={len(summary.actions_taken)} queued={len(summary.queued)} "
            f"alerts={len(summary.alerts)} anomalies={len(summary.anomalies)} "
            f"escalations={len(summary.escalations)} "
            f"blocked={len(summary.blocked)} errors={len(summary.errors)}"
        )
        return 1 if summary.errors else 0

    if args.command == "run":
        cfg, state, notifier = _load(args.config)
        run_loop(cfg, state, notifier, dry_run=args.dry_run, max_cycles=args.max_cycles)
        return 0

    if args.command == "list-pending":
        cfg, state, _ = _load(args.config)
        pending = state.list_pending()
        if not pending:
            print("no pending actions")
            return 0
        for e in pending:
            print(f"{e['id']}  {e['action']}  {e['target']}  — {e['reason']}")
        return 0

    if args.command == "approve":
        cfg, state, _ = _load(args.config)
        rec = approve(cfg, state, args.pending_id, dry_run=args.dry_run)
        if rec is None:
            print(f"no pending action with id {args.pending_id}", file=sys.stderr)
            return 2
        prefix = "(dry-run) " if args.dry_run else ""
        detail_source = rec.execution if rec.execution else rec.simulation
        details = detail_source.details if detail_source else []
        if rec.outcome in ("succeeded", "executed_unverified", "simulated_only"):
            print(f"{prefix}done ({rec.outcome}): {rec.decision.action} {rec.decision.target}")
            for d in details:
                print(f"  {d}")
            return 0
        if rec.outcome == "blocked":
            print(f"BLOCKED by safety gate: {'; '.join(rec.gate_reasons)}", file=sys.stderr)
            return 1
        if rec.outcome == "escalated":
            print(
                "ESCALATED: the action ran but the condition did not clear; "
                "a human needs to look. The agent will not retry.",
                file=sys.stderr,
            )
            return 1
        err = rec.execution.error if rec.execution else "unknown error"
        print(f"FAILED: {err}", file=sys.stderr)
        return 1

    if args.command == "deny":
        cfg, state, _ = _load(args.config)
        entry = deny(state, args.pending_id)
        if entry is None:
            print(f"no pending action with id {args.pending_id}", file=sys.stderr)
            return 2
        print(f"denied: {entry['action']} {entry['target']}")
        return 0

    if args.command == "history":
        cfg, state, _ = _load(args.config)
        records = state.list_history(args.limit)
        if not records:
            print("no history recorded yet")
            return 0
        for r in records:
            ts = r.get("ts")
            ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "?"
            outcome = r.get("outcome", "?")
            action = r.get("action", "?")
            target = r.get("target", "?")
            verified = r.get("verified")
            v_str = f" verified={verified}" if verified is not None else ""
            notes = "; ".join(r.get("notes", []))
            print(f"{ts_str}  {outcome:20s}  {action:20s}  {target}{v_str}")
            if notes:
                print(f"  → {notes}")
        return 0

    if args.command == "unblock-ip":
        from .remediation import ssh_unblock
        cfg, state, _ = _load(args.config)
        ip = args.ip
        res = ssh_unblock(ip, dry_run=args.dry_run)
        if res.error:
            print(f"ERROR: {res.error}", file=sys.stderr)
            return 1
        if not args.dry_run:
            state.unblock_ip(ip)
            state.save()
        for d in res.details:
            print(d)
        return 0

    if args.command == "list-blocked":
        cfg, state, _ = _load(args.config)
        blocked = state.list_blocked_ips()
        if not blocked:
            print("no blocked IPs")
            return 0
        now = time.time()
        for b in blocked:
            ip = b["ip"]
            blocked_at = b.get("blocked_at", 0)
            dur = b.get("duration_seconds", 0)
            if dur == 0:
                expires = "permanent"
            else:
                remaining = int(dur - (now - blocked_at))
                expires = f"expires in {max(0, remaining)}s"
            reason = b.get("reason", "")
            print(f"{ip:20s}  {expires}  — {reason}")
        return 0

    return 0  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
