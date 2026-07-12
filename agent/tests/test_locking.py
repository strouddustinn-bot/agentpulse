import json
import multiprocessing
import os
import subprocess
import sys
import time

import pytest

from agentpulse.locking import LockBusy, LockManager


def _hold_lock(directory, ready, release):
    manager = LockManager(directory)
    with manager.lock("agent-process", timeout=1):
        ready.send(True)
        release.recv()


def _try_lock(directory, result):
    manager = LockManager(directory)
    try:
        with manager.lock("agent-process", timeout=0.2):
            result.send("acquired")
    except LockBusy:
        result.send("busy")


def test_second_agent_process_is_rejected(tmp_path):
    ready_parent, ready_child = multiprocessing.Pipe()
    release_parent, release_child = multiprocessing.Pipe()
    first = multiprocessing.get_context("fork").Process(target=_hold_lock, args=(str(tmp_path), ready_child, release_child))
    first.start()
    assert ready_parent.recv() is True
    result_parent, result_child = multiprocessing.Pipe()
    second = multiprocessing.get_context("fork").Process(target=_try_lock, args=(str(tmp_path), result_child))
    second.start()
    assert result_parent.recv() == "busy"
    second.join(3)
    release_parent.send(True)
    first.join(3)
    assert first.exitcode == 0


def test_concurrent_checkin_is_rejected_or_serialized(tmp_path):
    manager = LockManager(tmp_path)
    with manager.lock("check-in", timeout=0.1):
        with pytest.raises(LockBusy):
            with manager.lock("check-in", timeout=0.05):
                pass


def test_distinct_remediation_resources_can_run_concurrently(tmp_path):
    manager = LockManager(tmp_path)
    with manager.lock("remediation:service-a", timeout=0.1):
        with manager.lock("remediation:service-b", timeout=0.1):
            pass


def test_same_remediation_resource_is_locked(tmp_path):
    manager = LockManager(tmp_path)
    first = manager.lock("remediation:service-a", timeout=0.1)
    first.acquire()
    try:
        with pytest.raises(LockBusy):
            with manager.lock("remediation:service-a", timeout=0.01):
                pass
    finally:
        first.release()


def test_lock_metadata_contains_pid_and_timestamp(tmp_path):
    manager = LockManager(tmp_path)
    with manager.lock("state", timeout=0.1):
        metadata = json.loads((tmp_path / "state.lock").read_text())
        assert metadata["pid"] == os.getpid()
        assert isinstance(metadata["timestamp"], str)


def test_context_manager_guarantees_release(tmp_path):
    manager = LockManager(tmp_path)
    with manager.lock("spool", timeout=0.1):
        pass
    with manager.lock("spool", timeout=0.1):
        pass


def test_stale_lock_metadata_is_recovered(tmp_path):
    path = tmp_path / "agent-process.lock"
    path.write_text(json.dumps({"pid": 99999999, "timestamp": "2000-01-01T00:00:00Z"}))
    manager = LockManager(tmp_path, stale_after=1)
    with manager.lock("agent-process", timeout=0.1):
        assert json.loads(path.read_text())["pid"] == os.getpid()


def test_lock_name_rejects_path_traversal(tmp_path):
    manager = LockManager(tmp_path)
    with pytest.raises(ValueError):
        manager.lock("../../etc/passwd")


def test_lock_timeout_uses_injected_sleep(tmp_path):
    sleeps = []
    manager = LockManager(tmp_path, poll_interval=0.2, sleep=sleeps.append)
    lock = manager.lock("state", timeout=0.1)
    lock.acquire()
    try:
        other = manager.lock("state", timeout=0.5)
        with pytest.raises(LockBusy):
            other.acquire()
        assert sleeps
    finally:
        lock.release()
        other.release()


def test_lock_files_are_private(tmp_path):
    manager = LockManager(tmp_path)
    with manager.lock("state", timeout=0.1):
        assert oct((tmp_path / "state.lock").stat().st_mode & 0o777) == "0o600"
        assert oct(tmp_path.stat().st_mode & 0o777) == "0o700"


def test_lock_release_is_idempotent(tmp_path):
    lock = LockManager(tmp_path).lock("state", timeout=0.1)
    lock.acquire()
    lock.release()
    lock.release()


def test_process_lock_survives_child_exit(tmp_path):
    # A process exit releases flock; the next process must acquire normally.
    ready_parent, ready_child = multiprocessing.Pipe()
    release_parent, release_child = multiprocessing.Pipe()
    first = multiprocessing.get_context("fork").Process(target=_hold_lock, args=(str(tmp_path), ready_child, release_child))
    first.start()
    assert ready_parent.recv() is True
    release_parent.send(True)
    first.join(3)
    manager = LockManager(tmp_path)
    with manager.lock("agent-process", timeout=0.2):
        assert True


def test_lock_owner_is_not_just_filename(tmp_path):
    manager = LockManager(tmp_path)
    with manager.lock("remediation:service/a", timeout=0.1) as lock:
        assert lock.path.name != "service/a.lock"
        assert lock.path.exists()
