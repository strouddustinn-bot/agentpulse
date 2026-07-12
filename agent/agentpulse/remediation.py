"""Remediation actions with hard safety guards.

Every action supports dry_run. Guards refuse anything dangerous *before*
touching the filesystem, systemd, processes, or iptables.

Actions:
    disk_cleanup    — delete old files matching configured globs
    service_restart — systemctl restart <service>
    process_kill    — SIGTERM + SIGKILL after grace period, with safety checks
    ssh_block       — iptables DROP for a brute-forcing IP
    ssh_unblock     — remove iptables DROP for an IP
"""

from __future__ import annotations

import glob as _glob
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .models import Decision

RunFn = Callable[[List[str]], "tuple[int, str]"]

_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")
_IP_RE = re.compile(
    r"^(\d{1,3}\.){3}\d{1,3}$"  # IPv4
    r"|^[0-9a-fA-F:]+$"          # IPv6 (simplified — iptables validates the rest)
)
_WILDCARD_CHARS = set("*?[")

# Process names that are ALWAYS off-limits regardless of config.
_HARD_NEVER_KILL = frozenset({
    "systemd", "init", "kthreadd", "kernel", "ksoftirqd",
    "migration", "watchdog", "kworker", "rcu_sched", "rcu_bh",
})

# iptables chains to check/use for blocking (prefer INPUT, fall back to FORWARD).
_IPTABLES_BLOCK_CHAIN = "INPUT"


@dataclass
class RemediationResult:
    action: str
    target: str
    performed: bool
    dry_run: bool
    details: List[str] = field(default_factory=list)
    bytes_freed: int = 0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _glob_base_dir(pattern: str) -> str:
    parts = pattern.split(os.sep)
    fixed = []
    for part in parts:
        if any(c in _WILDCARD_CHARS for c in part):
            break
        fixed.append(part)
    base = os.sep.join(fixed)
    return base or os.sep


def _is_safe_cleanup_glob(pattern: str) -> bool:
    if not pattern or not os.path.isabs(pattern):
        return False
    base = os.path.normpath(_glob_base_dir(pattern))
    depth = len([p for p in base.split(os.sep) if p])
    if base == os.sep or depth < 1:
        return False
    forbidden = {
        "/", "/bin", "/sbin", "/lib", "/lib64", "/usr", "/etc",
        "/boot", "/dev", "/proc", "/sys", "/root", "/home",
        "/var", "/usr/bin", "/usr/sbin",
    }
    return base not in forbidden


def _iptables_bin() -> Optional[str]:
    for cmd in ("iptables", "ip6tables"):
        try:
            proc = subprocess.run(
                [cmd, "--version"], capture_output=True, timeout=5, check=False
            )
            if proc.returncode == 0:
                return cmd
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


# ---------------------------------------------------------------------------
# disk_cleanup
# ---------------------------------------------------------------------------

def disk_cleanup(
    decision: Decision,
    dry_run: bool = False,
    now_fn: Callable[[], float] = time.time,
    glob_fn: Callable[[str], List[str]] = _glob.glob,
    isfile_fn: Callable[[str], bool] = os.path.isfile,
    islink_fn: Callable[[str], bool] = os.path.islink,
    getmtime_fn: Callable[[str], float] = os.path.getmtime,
    getsize_fn: Callable[[str], int] = os.path.getsize,
    remove_fn: Callable[[str], None] = os.remove,
) -> RemediationResult:
    obs = decision.observation
    meta = obs.metadata if obs else {}
    globs = meta.get("cleanup_globs", [])
    older_than_days = float(meta.get("cleanup_older_than_days", 3))
    cutoff = now_fn() - older_than_days * 86400.0

    result = RemediationResult(
        action="disk_cleanup", target=decision.target, performed=False, dry_run=dry_run
    )

    if not globs:
        result.error = "no cleanup_globs configured; refusing to guess what to delete"
        return result

    safe_globs = []
    for pattern in globs:
        if _is_safe_cleanup_glob(pattern):
            safe_globs.append(pattern)
        else:
            result.details.append(f"SKIP unsafe glob refused by guard: {pattern}")

    if not safe_globs:
        result.error = "all configured cleanup_globs were refused by the safety guard"
        return result

    freed = 0
    removed_any = False
    for pattern in safe_globs:
        for path in sorted(glob_fn(pattern)):
            if islink_fn(path) or not isfile_fn(path):
                continue
            try:
                if getmtime_fn(path) > cutoff:
                    continue
                size = getsize_fn(path)
            except OSError as exc:
                result.details.append(f"SKIP {path}: {exc}")
                continue
            if dry_run:
                result.details.append(f"WOULD remove {path} ({size} bytes)")
                freed += size
                removed_any = True
            else:
                try:
                    remove_fn(path)
                    result.details.append(f"removed {path} ({size} bytes)")
                    freed += size
                    removed_any = True
                except OSError as exc:
                    result.details.append(f"FAILED to remove {path}: {exc}")

    result.bytes_freed = freed
    result.performed = removed_any and not dry_run
    if not removed_any:
        result.details.append("no files matched the age/size criteria; nothing to clean")
    return result


# ---------------------------------------------------------------------------
# service_restart
# ---------------------------------------------------------------------------

def service_restart(
    decision: Decision,
    dry_run: bool = False,
    run_fn: RunFn = None,
) -> RemediationResult:
    if run_fn is None:
        from .checks import _default_run
        run_fn = _default_run

    obs = decision.observation
    svc = (obs.metadata.get("service") if obs else None) or decision.target
    result = RemediationResult(
        action="service_restart", target=svc, performed=False, dry_run=dry_run
    )

    if not svc or not _SERVICE_RE.match(svc):
        result.error = f"refusing to restart: invalid service name {svc!r}"
        return result

    if dry_run:
        result.details.append(f"WOULD run: systemctl restart {svc}")
        return result

    rc, out = run_fn(["systemctl", "restart", svc])
    if rc == 0:
        result.performed = True
        result.details.append(f"restarted {svc}")
    else:
        result.error = f"systemctl restart {svc} failed (rc={rc}): {out}"
    return result


# ---------------------------------------------------------------------------
# process_kill
# ---------------------------------------------------------------------------

def _read_proc_name(pid: int) -> Optional[str]:
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("Name:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def process_kill(
    decision: Decision,
    dry_run: bool = False,
    own_pid: int = None,
) -> RemediationResult:
    """Send SIGTERM to the target process, then SIGKILL after grace period.

    Hard safety rules (code-level, not config):
    - Never kill PID 1
    - Never kill the agent's own PID
    - Never kill processes whose name is in _HARD_NEVER_KILL
    - Verify the process name still matches before killing (PID reuse guard)
    - Kill_eligible flag must be set in observation metadata
    """
    obs = decision.observation
    meta = obs.metadata if obs else {}

    if own_pid is None:
        own_pid = os.getpid()

    result = RemediationResult(
        action="process_kill", target=decision.target, performed=False, dry_run=dry_run
    )

    pid = meta.get("pid")
    name = meta.get("name", "")
    grace = float(meta.get("kill_grace_seconds", 10))
    kill_eligible = meta.get("kill_eligible", False)

    if not pid:
        result.error = "no pid in observation metadata; refusing to kill without a target"
        return result

    pid = int(pid)

    # Hard safety checks.
    if pid == 1:
        result.error = "refusing to kill PID 1 (init/systemd)"
        return result
    if pid == own_pid:
        result.error = "refusing to kill the agent's own process"
        return result
    if name in _HARD_NEVER_KILL:
        result.error = f"refusing to kill {name!r}: in hard never-kill list"
        return result
    if not kill_eligible:
        result.error = (
            f"process {name!r} is not kill-eligible "
            "(not in kill_allowed_names or in never_kill list)"
        )
        return result

    # PID reuse guard: verify the process still exists and still has the same name.
    current_name = _read_proc_name(pid)
    if current_name is None:
        result.details.append(f"process {pid} no longer exists; nothing to kill")
        result.performed = False
        return result
    if current_name != name:
        result.error = (
            f"PID {pid} now has name {current_name!r}, expected {name!r}; "
            "refusing to kill (PID may have been reused)"
        )
        return result

    if dry_run:
        result.details.append(
            f"WOULD send SIGTERM to pid {pid} ({name}), "
            f"then SIGKILL after {grace}s if still running"
        )
        return result

    # Send SIGTERM.
    try:
        os.kill(pid, signal.SIGTERM)
        result.details.append(f"sent SIGTERM to pid {pid} ({name})")
    except ProcessLookupError:
        result.details.append(f"process {pid} already gone before SIGTERM")
        result.performed = True
        return result
    except PermissionError as exc:
        result.error = f"permission denied killing pid {pid}: {exc}"
        return result

    # Wait for grace period, then SIGKILL if still alive.
    deadline = time.time() + grace
    while time.time() < deadline:
        if _read_proc_name(pid) is None:
            result.details.append(f"process {pid} exited cleanly after SIGTERM")
            result.performed = True
            return result
        time.sleep(0.5)

    if _read_proc_name(pid) is not None:
        try:
            os.kill(pid, signal.SIGKILL)
            result.details.append(f"sent SIGKILL to pid {pid} ({name}) after {grace}s grace")
            result.performed = True
        except ProcessLookupError:
            result.details.append(f"process {pid} exited before SIGKILL")
            result.performed = True
        except PermissionError as exc:
            result.error = f"permission denied sending SIGKILL to pid {pid}: {exc}"
    else:
        result.performed = True

    return result


# ---------------------------------------------------------------------------
# ssh_block / ssh_unblock
# ---------------------------------------------------------------------------

def _validate_ip(ip: str) -> bool:
    return bool(_IP_RE.match(ip.strip()))


def ssh_block(
    decision: Decision,
    dry_run: bool = False,
    run_fn: RunFn = None,
) -> RemediationResult:
    """Block a brute-forcing IP with iptables DROP rule."""
    if run_fn is None:
        from .checks import _default_run
        run_fn = _default_run

    obs = decision.observation
    meta = obs.metadata if obs else {}
    ip = meta.get("ip") or decision.target

    result = RemediationResult(
        action="ssh_block", target=ip, performed=False, dry_run=dry_run
    )

    if not _validate_ip(ip):
        result.error = f"refusing to block: {ip!r} is not a valid IP address"
        return result

    # Detect iptables binary.
    ipt = _iptables_bin()
    if not ipt:
        result.error = "iptables/ip6tables not found; cannot block IP"
        return result

    if dry_run:
        result.details.append(
            f"WOULD run: {ipt} -I {_IPTABLES_BLOCK_CHAIN} -s {ip} -j DROP"
        )
        return result

    # Check if the rule already exists.
    rc_check, _ = run_fn([ipt, "-C", _IPTABLES_BLOCK_CHAIN, "-s", ip, "-j", "DROP"])
    if rc_check == 0:
        result.details.append(f"iptables DROP rule for {ip} already present")
        result.performed = True
        return result

    rc, out = run_fn([ipt, "-I", _IPTABLES_BLOCK_CHAIN, "-s", ip, "-j", "DROP"])
    if rc == 0:
        result.performed = True
        result.details.append(f"blocked {ip} via {ipt} {_IPTABLES_BLOCK_CHAIN} DROP")
    else:
        result.error = f"iptables block of {ip} failed (rc={rc}): {out}"
    return result


def ssh_unblock(
    ip: str,
    run_fn: RunFn = None,
    dry_run: bool = False,
) -> RemediationResult:
    """Remove the iptables DROP rule for an IP."""
    if run_fn is None:
        from .checks import _default_run
        run_fn = _default_run

    result = RemediationResult(
        action="ssh_unblock", target=ip, performed=False, dry_run=dry_run
    )

    if not _validate_ip(ip):
        result.error = f"refusing to unblock: {ip!r} is not a valid IP address"
        return result

    ipt = _iptables_bin()
    if not ipt:
        result.error = "iptables/ip6tables not found"
        return result

    if dry_run:
        result.details.append(
            f"WOULD run: {ipt} -D {_IPTABLES_BLOCK_CHAIN} -s {ip} -j DROP"
        )
        return result

    rc, out = run_fn([ipt, "-D", _IPTABLES_BLOCK_CHAIN, "-s", ip, "-j", "DROP"])
    if rc == 0:
        result.performed = True
        result.details.append(f"unblocked {ip}")
    else:
        result.details.append(f"unblock {ip}: {out or 'rule not found'}")
    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def execute(decision: Decision, dry_run: bool = False, run_fn: RunFn = None) -> RemediationResult:
    if decision.action == "disk_cleanup":
        return disk_cleanup(decision, dry_run=dry_run)
    if decision.action == "service_restart":
        return service_restart(decision, dry_run=dry_run, run_fn=run_fn)
    if decision.action == "process_kill":
        return process_kill(decision, dry_run=dry_run)
    if decision.action == "ssh_block":
        return ssh_block(decision, dry_run=dry_run, run_fn=run_fn)
    return RemediationResult(
        action=decision.action,
        target=decision.target,
        performed=False,
        dry_run=dry_run,
        details=["no remediation action for this check (alert only)"],
    )
