"""Watches the agent's state.json and samples host metrics.

StateWatcher.poll_once(): re-reads state.json when it changes (mtime_ns +
size, robust against coarse mtime granularity), mirrors new history rows into
SQLite, and emits SSE payloads via the injected ``emit`` callback. Missing or
invalid state files must NEVER crash the watcher — the dashboard outlives the
agent by design.

MetricSampler.sample_once(): reads /proc + disk usage directly (same host in
v1) and records chartable series.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from typing import Callable, Dict, List, Optional, Tuple

from .db import Db


def _as_list(value) -> List:
    """Normalize agent collections that may be a dict (id->entry) or a list."""
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return list(value)
    return []


class StateWatcher:
    """Read-only tail of the agent's state.json. Never writes the file."""

    def __init__(self, state_path: str, db: Db, emit: Callable[[dict], None]):
        self.state_path = state_path
        self.db = db
        self.emit = emit
        self._sig: Optional[Tuple[int, int]] = None  # (mtime_ns, size)
        self.snapshot: Dict = {}

    def poll_once(self) -> None:
        """Check for changes and ingest. Must never raise."""
        try:
            st = os.stat(self.state_path)
        except OSError:
            return  # agent not running / state not created yet: quiet
        sig = (st.st_mtime_ns, st.st_size)
        if sig == self._sig:
            return
        self._read_and_emit(sig)

    def force_refresh(self) -> None:
        """Re-read regardless of change detection (e.g. after approve/deny,
        where a sub-second rewrite could leave mtime unchanged)."""
        try:
            st = os.stat(self.state_path)
        except OSError:
            return
        self._read_and_emit((st.st_mtime_ns, st.st_size))

    def _read_and_emit(self, sig: Tuple[int, int]) -> None:
        try:
            with open(self.state_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            # ValueError covers json.JSONDecodeError. Log, don't advance the
            # signature: a partially-written file will be retried next poll.
            try:
                self.db.record_event("ingest_error", str(exc))
            except Exception:
                pass
            return
        if not isinstance(data, dict):
            try:
                self.db.record_event(
                    "ingest_error",
                    "state.json root is %s, expected object" % type(data).__name__)
            except Exception:
                pass
            self._sig = sig  # valid JSON, wrong shape — no point re-reading
            return

        self._sig = sig
        self.snapshot = data

        new_rows = 0
        hist = data.get("history")
        if isinstance(hist, list):
            for entry in hist:
                if isinstance(entry, dict) and self.db.record_history(entry):
                    new_rows += 1

        self.emit({
            "type": "state",
            "data": {
                "last_run": data.get("last_run"),
                "pending": _as_list(data.get("pending")),
                "blocked_ips": _as_list(data.get("blocked_ips")),
                "fleet": data.get("fleet", {}),
                "new_history": new_rows,
            },
        })
        if new_rows:
            self.emit({"type": "history", "data": self.db.history(limit=50)})


def _mem_percent() -> Optional[float]:
    try:
        info = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(":")] = int(parts[1])
        total = info["MemTotal"]
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        return round(100.0 * (total - avail) / total, 2)
    except (OSError, KeyError, ValueError, ZeroDivisionError):
        return None


def _load1() -> Optional[float]:
    try:
        return os.getloadavg()[0]
    except (OSError, AttributeError):
        return None


class MetricSampler:
    """Samples host memory %, 1-minute load, and disk usage % per path."""

    def __init__(self, db: Db, disk_paths: List[str],
                 emit: Callable[[dict], None]):
        self.db = db
        self.disk_paths = list(disk_paths)
        self.emit = emit

    def sample_once(self) -> None:
        """Record one sample of each metric. Must never raise."""
        ts = time.time()
        point: Dict[str, float] = {}
        mem = _mem_percent()
        if mem is not None:
            self.db.record_sample("mem", mem, ts)
            point["mem"] = mem
        load = _load1()
        if load is not None:
            self.db.record_sample("load1", load, ts)
            point["load1"] = load
        for path in self.disk_paths:
            try:
                du = shutil.disk_usage(path)
                pct = round(100.0 * du.used / du.total, 2)
            except (OSError, ZeroDivisionError):
                continue
            self.db.record_sample("disk:%s" % path, pct, ts)
            point["disk:%s" % path] = pct
        if point:
            self.emit({"type": "metrics", "data": {"ts": ts, "values": point}})
