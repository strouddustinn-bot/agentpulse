"""Windows compatibility boundary tests for the dependency-light agent package."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_modules_import_when_posix_fcntl_is_unavailable():
    script = """
import builtins
import subprocess  # Load the POSIX stdlib implementation before simulating Windows.

real_import = builtins.__import__


def import_without_fcntl(name, *args, **kwargs):
    if name == "fcntl":
        raise ModuleNotFoundError("No module named 'fcntl'")
    return real_import(name, *args, **kwargs)


builtins.__import__ = import_without_fcntl
import agentpulse.cli
import agentpulse.locking
import agentpulse.spool
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=AGENT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_lock_backed_features_fail_closed_without_fcntl():
    script = """
import builtins
import subprocess
import tempfile
from pathlib import Path

real_import = builtins.__import__


def import_without_fcntl(name, *args, **kwargs):
    if name == "fcntl":
        raise ModuleNotFoundError("No module named 'fcntl'")
    return real_import(name, *args, **kwargs)


builtins.__import__ = import_without_fcntl
from agentpulse.locking import LockManager
from agentpulse.platform_support import UnsupportedPlatformError
from agentpulse.spool import Spool

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    for factory in (lambda: LockManager(root / "locks"), lambda: Spool(root / "spool")):
        try:
            factory()
        except UnsupportedPlatformError as exc:
            assert "POSIX file locking" in str(exc)
        else:
            raise AssertionError("lock-backed feature did not fail closed")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=AGENT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_launchd_install_fails_before_filesystem_or_command_work_on_windows(tmp_path):
    from agentpulse import launchd

    calls = []
    state_dir = tmp_path / "state"
    log_path = tmp_path / "logs" / "agentpulse.log"
    plist_path = tmp_path / "LaunchDaemons" / "com.agentpulse.agent.plist"
    original_platform = sys.platform

    def fake_run(argv):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    try:
        sys.platform = "win32"
        try:
            launchd.install_launchd(
                agent_bin=str(tmp_path / "agentpulse.exe"),
                state_dir=str(state_dir),
                log_path=str(log_path),
                plist_path=str(plist_path),
                run_fn=fake_run,
            )
        except launchd.LaunchdInstallError as exc:
            assert str(exc) == "launchd installation is supported only on macOS"
        else:
            raise AssertionError("launchd install did not fail closed on Windows")
    finally:
        sys.platform = original_platform

    assert calls == []
    assert not state_dir.exists()
    assert not log_path.parent.exists()
    assert not plist_path.parent.exists()
