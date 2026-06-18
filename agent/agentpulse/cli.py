"""Command-line entrypoint for AgentPulse."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__, config as config_mod
from .notify import Notifier
from .runner import approve, run_loop, run_once
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
            f"alerts={len(summary.alerts)} escalations={len(summary.escalations)} "
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
        result = approve(cfg, state, args.pending_id, dry_run=args.dry_run)
        if result is None:
            print(f"no pending action with id {args.pending_id}", file=sys.stderr)
            return 2
        if result.ok:
            print(f"{'(dry-run) ' if args.dry_run else ''}done: {result.action} {result.target}")
            for d in result.details:
                print(f"  {d}")
            return 0
        print(f"FAILED: {result.error}", file=sys.stderr)
        return 1

    return 0  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
