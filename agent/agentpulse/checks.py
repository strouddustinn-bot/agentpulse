"""Host checks. Each returns a list of Observation.

All OS interactions are injected (disk_usage_fn, run_fn, proc reader) so the
checks can be unit-tested deterministically without a real server.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from typing import Callable, Dict, List, Optional, Tuple

from .config import (
    Config,
    DiskCheckConfig,
    ProcessCheckConfig,
    ServiceCheckConfig,
    SshCheckConfig,
)
from .models import Observation

DiskUsageFn = Callable[[str], Tuple[int, int, int]]
RunFn = Callable[[List[str]], Tuple[int, str]]

# auth.log failure patterns — matches OpenSSH "Failed password", "Invalid user",
# "Connection closed by invalid user", PAM auth failures, and common variants.
_SSH_FAIL_RE = re.compile(
    r"(?:Failed (?:password|publickey|keyboard-interactive)"
    r"|Invalid user \S+"
    r"|Connection closed by (?:invalid user|authenticating user)"
    r"|Did not receive identification string"
    r"|maximum authentication attempts exceeded)"
    r".*?(?:from|authenticating user \S+ from)\s+(\d{1,3}(?:\.\d{1,3}){3}|\S+:\S*:\S*)",
    re.IGNORECASE,
)
_SSH_LOG_CANDIDATES = ["/var/log/auth.log", "/var/log/secure", "/var/log/messages"]


def _default_disk_usage(path: str) -> Tuple[int, int, int]:
    u = shutil.disk_usage(path)
    return u.total, u.used, u.free


def _default_run(argv: List[str]) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=15, check=False
        )
        return proc.returncode, (proc.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def check_disk(
    cfg: DiskCheckConfig, disk_usage_fn: DiskUsageFn = _default_disk_usage
) -> List[Observation]:
    out: List[Observation] = []
    for path in cfg.paths:
        try:
            total, used, _free = disk_usage_fn(path)
        except OSError as exc:
            out.append(
                Observation(
                    check="disk",
                    target=path,
                    breached=False,
                    detail=f"could not read disk usage for {path}: {exc}",
                )
            )
            continue
        percent = (used / total * 100.0) if total else 0.0
        breached = percent >= cfg.threshold_percent
        out.append(
            Observation(
                check="disk",
                target=path,
                breached=breached,
                value=round(percent, 1),
                detail=(
                    f"disk {path} at {percent:.1f}% "
                    f"(threshold {cfg.threshold_percent:.0f}%)"
                ),
                metadata={
                    "cleanup_globs": list(cfg.cleanup_globs),
                    "cleanup_older_than_days": cfg.cleanup_older_than_days,
                    "percent": round(percent, 1),
                },
            )
        )
    return out


def check_services(
    cfg: ServiceCheckConfig, run_fn: RunFn = _default_run
) -> List[Observation]:
    out: List[Observation] = []
    for svc in cfg.services:
        rc, stdout = run_fn(["systemctl", "is-active", svc])
        active = rc == 0 and stdout.strip() == "active"
        out.append(
            Observation(
                check="service",
                target=svc,
                breached=not active,
                detail=(
                    f"service {svc} is active"
                    if active
                    else f"service {svc} is {stdout or 'not active'}"
                ),
                metadata={"service": svc, "state": stdout},
            )
        )
    return out


def _read_meminfo_total_kb(proc_root: str) -> Optional[int]:
    try:
        with open(os.path.join(proc_root, "meminfo"), "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1])
    except (OSError, ValueError):
        return None
    return None


def _iter_proc_rss(proc_root: str):
    """Yield (pid, name, rss_kb) for each process under proc_root."""
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return
    for entry in entries:
        if not entry.isdigit():
            continue
        status_path = os.path.join(proc_root, entry, "status")
        name = ""
        rss_kb = 0
        try:
            with open(status_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("Name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("VmRSS:"):
                        rss_kb = int(line.split()[1])
        except (OSError, ValueError):
            continue
        yield int(entry), name, rss_kb


def host_memory_percent(proc_root: str = "/proc") -> Optional[float]:
    total = avail = free = None
    try:
        with open(os.path.join(proc_root, "meminfo"), "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail = int(line.split()[1])
                elif line.startswith("MemFree:"):
                    free = int(line.split()[1])
    except (OSError, ValueError):
        return None
    if not total:
        return None
    usable = avail if avail is not None else free
    if usable is None:
        return None
    return round((1.0 - usable / total) * 100.0, 1)


def check_processes(
    cfg: ProcessCheckConfig, proc_root: str = "/proc"
) -> List[Observation]:
    """Flag the single largest memory-consuming process if it exceeds threshold.

    In auto mode, the process can be killed subject to per-name allowlist and
    safety gates in the decision loop. In alert/ask modes, it is reported only.
    """
    mem_total = _read_meminfo_total_kb(proc_root)
    if not mem_total:
        return []

    worst = None  # (percent, pid, name, rss_kb)
    for pid, name, rss_kb in _iter_proc_rss(proc_root):
        percent = rss_kb / mem_total * 100.0
        if worst is None or percent > worst[0]:
            worst = (percent, pid, name, rss_kb)

    if worst is None:
        return []

    percent, pid, name, rss_kb = worst
    breached = percent >= cfg.mem_percent_threshold
    if not breached:
        return []

    kill_eligible = (
        not cfg.kill_allowed_names or name in cfg.kill_allowed_names
    ) and name not in cfg.never_kill

    return [
        Observation(
            check="process",
            target=f"pid:{pid} ({name})",
            breached=True,
            value=round(percent, 1),
            detail=(
                f"process {name} (pid {pid}) using {percent:.1f}% of memory "
                f"(threshold {cfg.mem_percent_threshold:.0f}%)"
            ),
            metadata={
                "pid": pid,
                "name": name,
                "rss_kb": rss_kb,
                "percent": round(percent, 1),
                "kill_eligible": kill_eligible,
                "kill_grace_seconds": cfg.kill_grace_seconds,
            },
        )
    ]


def _detect_ssh_log() -> str:
    for candidate in _SSH_LOG_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return ""


def _parse_auth_log(
    log_file: str,
    window_seconds: int,
    now: float,
) -> Dict[str, int]:
    """Return {ip: failure_count} for the trailing window_seconds of log_file."""
    cutoff = now - window_seconds
    counts: Dict[str, int] = {}
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as fh:
            # Read last 50 KB — enough for a brute-force burst without
            # scanning the whole log on every cycle.
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 50_000))
            lines = fh.readlines()
    except OSError:
        return {}

    current_year = time.localtime(now).tm_year
    import datetime as _dt

    for line in lines:
        m = _SSH_FAIL_RE.search(line)
        if not m:
            continue
        ip = m.group(1)
        # Parse the log timestamp (e.g. "Jun 27 03:14:15")
        # If parsing fails, include the line conservatively.
        parts = line.split()
        if len(parts) >= 3:
            try:
                ts_str = f"{parts[0]} {parts[1]} {parts[2]} {current_year}"
                ts = _dt.datetime.strptime(ts_str, "%b %d %H:%M:%S %Y").timestamp()
                # Handle year wrap (log near Jan 1 might show Dec timestamps)
                if ts > now + 86400:
                    ts -= 365 * 86400
                if ts < cutoff:
                    continue
            except (ValueError, IndexError):
                pass  # include the line if we can't parse the timestamp
        counts[ip] = counts.get(ip, 0) + 1

    return counts


def check_ssh(
    cfg: SshCheckConfig,
    log_file: Optional[str] = None,
    now: Optional[float] = None,
) -> List[Observation]:
    """Detect SSH brute-force attempts. Returns one Observation per offending IP."""
    if now is None:
        now = time.time()
    log = log_file or cfg.log_file or _detect_ssh_log()
    if not log:
        return [
            Observation(
                check="ssh",
                target="auth.log",
                breached=False,
                detail="no auth log found; ssh check skipped",
            )
        ]

    counts = _parse_auth_log(log, cfg.window_seconds, now)
    out: List[Observation] = []
    for ip, count in counts.items():
        if count < cfg.failure_threshold:
            continue
        if ip in cfg.never_block:
            continue
        out.append(
            Observation(
                check="ssh",
                target=ip,
                breached=True,
                value=float(count),
                detail=(
                    f"{count} failed SSH attempts from {ip} in the last "
                    f"{cfg.window_seconds}s (threshold {cfg.failure_threshold})"
                ),
                metadata={
                    "ip": ip,
                    "failure_count": count,
                    "window_seconds": cfg.window_seconds,
                    "block_duration_seconds": cfg.block_duration_seconds,
                },
            )
        )
    return out


def gather(cfg: Config) -> List[Observation]:
    """Run every enabled check and return all observations."""
    observations: List[Observation] = []
    if cfg.disk.mode != "off":
        observations.extend(check_disk(cfg.disk))
    if cfg.service.mode != "off":
        observations.extend(check_services(cfg.service))
    if cfg.process.mode != "off":
        observations.extend(check_processes(cfg.process))
    if cfg.ssh.mode != "off":
        observations.extend(check_ssh(cfg.ssh))
    return observations
