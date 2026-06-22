"""Remediation actions with hard safety guards.

Every action supports dry_run. Guards refuse anything dangerous (root-level
globs, non-allowlisted services, symlinks, directories) *before* touching the
filesystem or systemd.
"""

from __future__ import annotations

import glob as _glob
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .models import Decision

RunFn = Callable[[List[str]], "tuple[int, str]"]

_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")
_WILDCARD_CHARS = set("*?[")


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


def _glob_base_dir(pattern: str) -> str:
    """Return the fixed directory portion of a glob (before any wildcard)."""
    parts = pattern.split(os.sep)
    fixed = []
    for part in parts:
        if any(c in _WILDCARD_CHARS for c in part):
            break
        fixed.append(part)
    base = os.sep.join(fixed)
    return base or os.sep


def _is_safe_cleanup_glob(pattern: str) -> bool:
    """Refuse globs that could sweep the whole filesystem."""
    if not pattern or not os.path.isabs(pattern):
        return False
    base = os.path.normpath(_glob_base_dir(pattern))
    # Require the fixed base to be at least two levels deep (e.g. /tmp is fine,
    # /var/log/app is fine; "/" or "/*" is not).
    depth = len([p for p in base.split(os.sep) if p])
    if base == os.sep or depth < 1:
        return False
    # Explicitly forbid the most dangerous bases even at depth 1 we keep /tmp
    # allowed but block obviously catastrophic roots.
    forbidden = {"/", "/bin", "/sbin", "/lib", "/lib64", "/usr", "/etc", "/boot", "/dev", "/proc", "/sys", "/root", "/home", "/var", "/usr/bin", "/usr/sbin"}
    if base in forbidden:
        return False
    return True


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
                continue  # never follow symlinks or delete directories
            try:
                if getmtime_fn(path) > cutoff:
                    continue  # too new
                size = getsize_fn(path)
            except OSError as exc:  # pragma: no cover - env dependent
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
                except OSError as exc:  # pragma: no cover - env dependent
                    result.details.append(f"FAILED to remove {path}: {exc}")

    result.bytes_freed = freed
    result.performed = removed_any and not dry_run
    if not removed_any:
        result.details.append("no files matched the age/size criteria; nothing to clean")
    return result


def service_restart(
    decision: Decision,
    dry_run: bool = False,
    run_fn: RunFn = None,
) -> RemediationResult:
    if run_fn is None:
        from .checks import _default_run  # local import to avoid cycle at import time

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


def execute(decision: Decision, dry_run: bool = False, run_fn: RunFn = None) -> RemediationResult:
    """Dispatch a decision whose action should actually run."""
    if decision.action == "disk_cleanup":
        # disk_cleanup does no subprocess work, so run_fn (the subprocess
        # runner) does not apply; it has its own filesystem-fn injection points.
        return disk_cleanup(decision, dry_run=dry_run)
    if decision.action == "service_restart":
        return service_restart(decision, dry_run=dry_run, run_fn=run_fn)
    # process_alert / none have no remediation in v1.
    return RemediationResult(
        action=decision.action,
        target=decision.target,
        performed=False,
        dry_run=dry_run,
        details=["no remediation action for this check in v1 (alert only)"],
    )
