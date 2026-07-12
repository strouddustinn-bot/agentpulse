"""Safe macOS launchd installer for AgentPulse."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional

DEFAULT_LABEL = "com.agentpulse.agent"
DEFAULT_CONFIG_PATH = "/usr/local/etc/agentpulse/config.json"
DEFAULT_LOG_PATH = "/usr/local/var/log/agentpulse/agentpulse.log"
DEFAULT_STATE_DIR = "/usr/local/var/lib/agentpulse"


class LaunchdInstallError(RuntimeError):
    """Raised when launchd installation cannot be completed safely."""


@dataclass
class LaunchdInstallResult:
    label: str
    agent_bin: str
    config_path: str
    log_path: str
    plist_path: str
    state_dir: str
    dry_run: bool
    steps: List[str] = field(default_factory=list)


def _validate_label(label: str) -> str:
    if not label or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_" for ch in label):
        raise LaunchdInstallError(f"invalid launchd label: {label!r}")
    return label


def _plist_bytes(label: str, agent_bin: str, config_path: str, log_path: str) -> bytes:
    payload = {
        "Label": label,
        "ProgramArguments": [agent_bin, "run", config_path],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
        "ProcessType": "Background",
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)


def install_launchd(
    *,
    label: str = DEFAULT_LABEL,
    agent_bin: Optional[str] = None,
    config_path: str = DEFAULT_CONFIG_PATH,
    log_path: str = DEFAULT_LOG_PATH,
    plist_path: Optional[str] = None,
    state_dir: str = DEFAULT_STATE_DIR,
    dry_run: bool = False,
    run_fn: Optional[Callable[[List[str]], subprocess.CompletedProcess]] = None,
) -> LaunchdInstallResult:
    """Install and bootstrap a system LaunchDaemon, or return an exact dry-run plan."""
    label = _validate_label(label)
    resolved_bin = agent_bin or shutil.which("agentpulse")
    if not resolved_bin:
        raise LaunchdInstallError("agentpulse executable was not found; pass --agent-bin")
    resolved_bin = os.path.abspath(resolved_bin)
    target_plist = plist_path or f"/Library/LaunchDaemons/{label}.plist"
    steps = [
        f"create state directory {state_dir}",
        f"create log directory {os.path.dirname(log_path)}",
        f"write plist {target_plist} with mode 0644",
        f"bootstrap launchd service {label}",
    ]
    result = LaunchdInstallResult(
        label=label,
        agent_bin=resolved_bin,
        config_path=os.path.abspath(config_path),
        log_path=os.path.abspath(log_path),
        plist_path=os.path.abspath(target_plist),
        state_dir=os.path.abspath(state_dir),
        dry_run=dry_run,
        steps=steps,
    )
    if dry_run:
        return result

    os.makedirs(result.state_dir, mode=0o750, exist_ok=True)
    os.makedirs(os.path.dirname(result.log_path), mode=0o750, exist_ok=True)
    os.makedirs(os.path.dirname(result.plist_path), mode=0o755, exist_ok=True)
    temporary = result.plist_path + ".tmp"
    try:
        with open(temporary, "wb") as handle:
            handle.write(
                _plist_bytes(
                    result.label,
                    result.agent_bin,
                    result.config_path,
                    result.log_path,
                )
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, result.plist_path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass

    runner = run_fn or (lambda argv: subprocess.run(argv, capture_output=True, text=True, check=False))
    completed = runner(["launchctl", "bootstrap", "system", result.plist_path])
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown launchctl error").strip()
        raise LaunchdInstallError(f"launchctl bootstrap failed: {detail}")
    return result
