"""Host checks. Each returns a list of Observation.

All OS interactions are injected (disk_usage_fn, run_fn, proc reader) so the
checks can be unit-tested deterministically without a real server.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Callable, List, Optional, Tuple

from .config import (
    Config,
    DiskCheckConfig,
    ProcessCheckConfig,
    ServiceCheckConfig,
)
from .models import Observation

DiskUsageFn = Callable[[str], Tuple[int, int, int]]  # path -> (total, used, free)
RunFn = Callable[[List[str]], Tuple[int, str]]  # argv -> (returncode, stdout)


def _default_disk_usage(path: str) -> Tuple[int, int, int]:
    u = shutil.disk_usage(path)
    return u.total, u.used, u.free


def _default_run(argv: List[str]) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=15, check=False
        )
        return proc.returncode, (proc.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover - env dependent
        return 1, str(exc)


def check_disk(
    cfg: DiskCheckConfig, disk_usage_fn: DiskUsageFn = _default_disk_usage
) -> List[Observation]:
    out: List[Observation] = []
    for path in cfg.paths:
        try:
            total, used, _free = disk_usage_fn(path)
        except OSError as exc:  # pragma: no cover - env dependent
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
    except (OSError, ValueError):  # pragma: no cover - env dependent
        return None
    return None


def _iter_proc_rss(proc_root: str):
    """Yield (pid, name, rss_kb) for each process under proc_root."""
    try:
        entries = os.listdir(proc_root)
    except OSError:  # pragma: no cover - env dependent
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
    """Return host memory used percent, or None if unreadable.

    used% = (1 - MemAvailable/MemTotal) * 100, falling back to MemFree.
    """
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
    except (OSError, ValueError):  # pragma: no cover - env dependent
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
    """Flag the single largest process if it exceeds the memory threshold.

    v1 only reports memory-runaway; it never kills. Reporting the top offender
    (not every process) keeps alerts actionable.
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
            metadata={"pid": pid, "name": name, "rss_kb": rss_kb, "percent": round(percent, 1)},
        )
    ]


def gather(cfg: Config) -> List[Observation]:
    """Run every enabled check and return all observations."""
    observations: List[Observation] = []
    if cfg.disk.mode != "off":
        observations.extend(check_disk(cfg.disk))
    if cfg.service.mode != "off":
        observations.extend(check_services(cfg.service))
    if cfg.process.mode != "off":
        observations.extend(check_processes(cfg.process))
    return observations
