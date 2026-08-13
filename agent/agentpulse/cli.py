"""Command-line entrypoint for AgentPulse."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
from typing import List, Optional

from . import __version__
from . import config as config_mod
from . import control_plane
from . import launchd as launchd_installer
from . import windows_service
from .checkin import (
    CheckinDeliveryError,
    build_checkin_payload,
    payload_to_json,
    send_checkin_payload,
)
from .notify import Notifier
from .runner import approve, deny, run_loop, run_once
from .state import State


class _SilentNotifier:
    def send(self, title: str, body: str) -> bool:
        return True


def _load(config_path: str):
    cfg = config_mod.load(config_path)
    state = State.load(cfg.state_file)
    notifier = Notifier(cfg.notify)
    return cfg, state, notifier


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agentpulse", description="AgentPulse monitoring + remediation agent"
    )
    p.add_argument("--version", action="version", version=f"agentpulse {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    pv = sub.add_parser("validate", help="validate a config file")
    pv.add_argument("config")

    pr = sub.add_parser("run-once", help="run a single check/remediate cycle")
    pr.add_argument("config")
    pr.add_argument(
        "--dry-run",
        action="store_true",
        help="never modify the system; report what would happen",
    )

    pc = sub.add_parser("check-in", help="build an agent check-in payload")
    pc.add_argument("config")
    pc.add_argument(
        "--dry-run", action="store_true", help="print payload without sending it"
    )

    pl = sub.add_parser("run", help="run continuously on the configured interval")
    pl.add_argument("config")
    pl.add_argument("--dry-run", action="store_true")
    pl.add_argument(
        "--max-cycles", type=int, default=None, help="stop after N cycles (testing)"
    )

    pp = sub.add_parser("list-pending", help="list ask-first actions awaiting approval")
    pp.add_argument("config")

    pa = sub.add_parser(
        "approve", help="approve and execute a pending ask-first action"
    )
    pa.add_argument("config")
    pa.add_argument("pending_id")
    pa.add_argument("--dry-run", action="store_true")

    pd = sub.add_parser("deny", help="reject a pending ask-first action")
    pd.add_argument("config")
    pd.add_argument("pending_id")

    ph = sub.add_parser("history", help="show recent action history")
    ph.add_argument("config")
    ph.add_argument("--limit", type=int, default=20)

    pe = sub.add_parser("enroll", help="enroll this host with the SaaS control plane")
    pe.add_argument("config")
    pe.add_argument(
        "--token-stdin",
        action="store_true",
        help="read the one-time enrollment token from stdin instead of process arguments",
    )
    pe.add_argument("--agent-key", default=None)

    pil = sub.add_parser(
        "install-launchd",
        help="install AgentPulse as a macOS launchd daemon",
    )
    pil.add_argument(
        "--label",
        default=launchd_installer.DEFAULT_LABEL,
        help="launchd label to install",
    )
    pil.add_argument(
        "--agent-bin",
        default=None,
        help="path to the agentpulse executable (defaults to PATH lookup)",
    )
    pil.add_argument(
        "--config",
        default=launchd_installer.DEFAULT_CONFIG_PATH,
        help="config path for the daemon",
    )
    pil.add_argument(
        "--log",
        default=launchd_installer.DEFAULT_LOG_PATH,
        help="combined stdout/stderr log path for launchd",
    )
    pil.add_argument(
        "--plist",
        default=None,
        help="plist destination (defaults to /Library/LaunchDaemons/<label>.plist)",
    )
    pil.add_argument(
        "--state-dir",
        default=launchd_installer.DEFAULT_STATE_DIR,
        help="directory for AgentPulse state on macOS",
    )
    pil.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be installed without writing files or calling launchctl",
    )

    pwin = sub.add_parser(
        "install-windows-service",
        help="install AgentPulse as a checksum-verified WinSW service",
    )
    pwin.add_argument("--winsw-bin", required=True, help="path to WinSW-x64.exe")
    pwin.add_argument(
        "--winsw-sha256",
        default=windows_service.WINSW_X64_SHA256,
        help=f"expected WinSW SHA-256 (defaults to pinned v{windows_service.WINSW_VERSION})",
    )
    pwin.add_argument(
        "--service-id",
        default=windows_service.DEFAULT_SERVICE_ID,
        help="alphanumeric Windows service ID",
    )
    pwin.add_argument(
        "--display-name",
        default=windows_service.DEFAULT_DISPLAY_NAME,
        help="Windows Services display name",
    )
    pwin.add_argument(
        "--agent-bin",
        default=None,
        help="path to agentpulse.exe (defaults to PATH lookup)",
    )
    pwin.add_argument("--config", required=True, help="absolute AgentPulse config path")
    pwin.add_argument(
        "--install-dir",
        default=None,
        help=r"service wrapper directory (defaults to %ProgramData%\AgentPulse\service)",
    )
    pwin.add_argument(
        "--log-dir",
        default=None,
        help=r"service log directory (defaults to %ProgramData%\AgentPulse\logs)",
    )
    pwin.add_argument("--dry-run", action="store_true")

    puwin = sub.add_parser(
        "uninstall-windows-service",
        help="stop and uninstall the AgentPulse WinSW service",
    )
    puwin.add_argument(
        "--service-id",
        default=windows_service.DEFAULT_SERVICE_ID,
        help="alphanumeric Windows service ID",
    )
    puwin.add_argument(
        "--install-dir",
        default=None,
        help=r"service wrapper directory (defaults to %ProgramData%\AgentPulse\service)",
    )
    puwin.add_argument(
        "--remove-files",
        action="store_true",
        help="remove only the generated wrapper executable and XML after uninstall",
    )
    puwin.add_argument("--dry-run", action="store_true")

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

    if args.command == "check-in":
        cfg, state, _ = _load(args.config)
        summary = run_once(cfg, state, _SilentNotifier(), dry_run=True)
        payload = build_checkin_payload(cfg, summary)

        if args.dry_run:
            print(payload_to_json(payload))
            return 1 if summary.errors else 0

        try:
            status = send_checkin_payload(cfg, payload)
        except CheckinDeliveryError as exc:
            print(f"CHECK-IN FAILED: {exc}", file=sys.stderr)
            return 2

        print(f"check-in delivered status={status}")
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
            print(
                f"{prefix}done ({rec.outcome}): {rec.decision.action} {rec.decision.target}"
            )
            for d in details:
                print(f"  {d}")
            return 0
        if rec.outcome == "blocked":
            print(
                f"BLOCKED by safety gate: {'; '.join(rec.gate_reasons)}",
                file=sys.stderr,
            )
            return 1
        if rec.outcome == "escalated":
            print(
                "ESCALATED: the action ran but the condition did not clear; "
                "a human needs to look. The agent will not retry.",
                file=sys.stderr,
            )
            return 1
        # failed
        err = rec.execution.error if rec.execution else "unknown error"
        print(f"FAILED: {err}", file=sys.stderr)
        return 1

    if args.command == "deny":
        _, state, _ = _load(args.config)
        entry = deny(state, args.pending_id)
        if entry is None:
            print(f"no pending action with id {args.pending_id}", file=sys.stderr)
            return 2
        print(f"denied: {entry['action']} {entry['target']}")
        return 0

    if args.command == "history":
        _, state, _ = _load(args.config)
        for record in state.list_history(args.limit):
            ts = record.get("ts")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "?"
            print(
                f"{timestamp}  {record.get('outcome', '?'):20s}  "
                f"{record.get('action', '?'):20s}  {record.get('target', '?')}"
            )
        return 0

    if args.command == "enroll":
        cfg = config_mod.load(args.config)
        if not cfg.control_plane.enabled:
            print("control_plane.enabled must be true before enrollment", file=sys.stderr)
            return 2
        if args.token_stdin:
            enrollment_token = sys.stdin.readline().rstrip("\r\n")
        else:
            enrollment_token = getpass.getpass("One-time enrollment token: ")
        if not enrollment_token:
            print("a non-empty enrollment token is required", file=sys.stderr)
            return 2
        try:
            result = control_plane.enroll(
                base_url=cfg.control_plane.base_url,
                enrollment_token=enrollment_token,
                agent_key=args.agent_key or cfg.resolved_hostname(),
                hostname=cfg.resolved_hostname(),
                local_policy_ceiling=cfg.control_plane.local_policy_ceiling,
                credential_file=cfg.control_plane.credential_file,
                timeout=cfg.control_plane.timeout_seconds,
            )
        except (control_plane.ControlPlaneError, control_plane.CredentialError) as exc:
            print(f"ENROLLMENT FAILED: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, sort_keys=True))
        return 0

    if args.command == "install-launchd":
        try:
            result = launchd_installer.install_launchd(
                label=args.label,
                agent_bin=args.agent_bin,
                config_path=args.config,
                log_path=args.log,
                plist_path=args.plist,
                state_dir=args.state_dir,
                dry_run=args.dry_run,
            )
        except launchd_installer.LaunchdInstallError as exc:
            print(f"INSTALL-LAUNCHD FAILED: {exc}", file=sys.stderr)
            return 2

        prefix = "would install" if result.dry_run else "installed"
        print(f"AgentPulse launchd daemon {prefix}: {result.label}")
        print(f"  binary: {result.agent_bin}")
        print(f"  config: {result.config_path}")
        print(f"  log:    {result.log_path}")
        print(f"  plist:  {result.plist_path}")
        if result.dry_run:
            for step in result.steps:
                print(f"  - {step}")
        return 0

    if args.command == "install-windows-service":
        try:
            result = windows_service.install_windows_service(
                winsw_bin=args.winsw_bin,
                winsw_sha256=args.winsw_sha256,
                service_id=args.service_id,
                display_name=args.display_name,
                agent_bin=args.agent_bin,
                config_path=args.config,
                install_dir=args.install_dir,
                log_dir=args.log_dir,
                dry_run=args.dry_run,
            )
        except windows_service.WindowsServiceError as exc:
            print(f"INSTALL-WINDOWS-SERVICE FAILED: {exc}", file=sys.stderr)
            return 2
        prefix = "would install" if result.dry_run else "installed"
        print(f"AgentPulse Windows service {prefix}: {result.service_id}")
        print(f"  binary: {result.agent_bin}")
        print(f"  config: {result.config_path}")
        print(f"  wrapper: {result.wrapper_path}")
        print(f"  logs:    {result.log_dir}")
        if result.dry_run:
            for step in result.steps:
                print(f"  - {step}")
        return 0

    if args.command == "uninstall-windows-service":
        try:
            steps = windows_service.uninstall_windows_service(
                service_id=args.service_id,
                install_dir=args.install_dir,
                remove_files=args.remove_files,
                dry_run=args.dry_run,
            )
        except windows_service.WindowsServiceError as exc:
            print(f"UNINSTALL-WINDOWS-SERVICE FAILED: {exc}", file=sys.stderr)
            return 2
        prefix = "would uninstall" if args.dry_run else "uninstalled"
        print(f"AgentPulse Windows service {prefix}: {args.service_id}")
        if args.dry_run:
            for step in steps:
                print(f"  - {step}")
        return 0

    return 0  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
