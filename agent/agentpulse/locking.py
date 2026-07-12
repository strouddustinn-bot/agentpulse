"""Named inter-process locks with bounded acquisition and stale recovery."""
from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional


class LockBusy(TimeoutError):
    """A named lock could not be acquired before its deadline."""


class LockHandle:
    def __init__(self, manager: "LockManager", name: str, timeout: float) -> None:
        self.manager = manager
        self.name = name
        self.timeout = timeout
        self.path = manager._path(name)
        self._file = None
        self._acquired = False

    def acquire(self) -> "LockHandle":
        if self._acquired:
            return self
        deadline = self.manager.clock() + self.timeout
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        handle = self.path.open("a+", encoding="utf-8")
        os.chmod(self.path, 0o600)
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._file = handle
                self._acquired = True
                handle.seek(0)
                handle.truncate()
                json.dump({"pid": os.getpid(), "timestamp": _now()}, handle)
                handle.flush()
                os.fsync(handle.fileno())
                return self
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    handle.close()
                    raise
                # Metadata belongs to the current lock holder; do not unlink a
                # live flock. A dead/stale file is harmless and overwritten once
                # the kernel lock becomes available.
                if self.manager.clock() >= deadline:
                    handle.close()
                    raise LockBusy(f"lock busy: {self.name}")
                self.manager.sleep(min(self.manager.poll_interval, max(0.0, deadline - self.manager.clock())))

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None
            self._acquired = False

    def __enter__(self) -> "LockHandle":
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()


class LockManager:
    def __init__(self, directory: os.PathLike[str] | str, *, stale_after: float = 300.0, poll_interval: float = 0.05, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        self.directory = Path(directory)
        self.stale_after = stale_after
        self.poll_interval = max(0.001, poll_interval)
        self.sleep = sleep
        self.clock = clock
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)

    def lock(self, name: str, timeout: float = 5.0) -> LockHandle:
        self._path(name)
        return LockHandle(self, name, timeout)

    def _path(self, name: str) -> Path:
        if not name or ".." in name or not re.fullmatch(r"[A-Za-z0-9:_./-]+", name):
            raise ValueError("invalid lock name")
        safe = name.replace("/", "__")
        return self.directory / f"{safe}.lock"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = ["LockBusy", "LockHandle", "LockManager"]
