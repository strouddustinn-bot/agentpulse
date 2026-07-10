"""SQLite persistence for the dashboard service.

Tables:
  history        — mirror of agent history, unbounded (agent caps at 200)
  metric_samples — host metric time series for charts
  events         — service-level event log (ingest errors, UI actions)

Stdlib sqlite3, WAL mode, no ORM. All statements are parameterized. A single
threading.Lock serializes access because the connection is shared between the
background ingest thread and request handlers.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    outcome TEXT NOT NULL,
    dedupe_key TEXT UNIQUE,
    raw TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_ts ON history(ts);

CREATE TABLE IF NOT EXISTS metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_metric_ts ON metric_samples(metric, ts);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


class Db:
    """Thread-safe SQLite layer. Safe to share across threads."""

    def __init__(self, path: str):
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close the connection. Idempotent; used by tests and shutdown."""
        with self._lock:
            self._conn.close()  # sqlite3 tolerates repeated close()

    # -- history ------------------------------------------------------------

    def record_history(self, entry: Dict[str, Any]) -> bool:
        """Insert a history record; True if new (dedupe on ts+action+target)."""
        key = "%s:%s:%s" % (entry.get("ts"), entry.get("action"),
                            entry.get("target"))
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO history (ts, action, target, outcome,"
                    " dedupe_key, raw) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        float(entry.get("ts") or time.time()),
                        str(entry.get("action", "")),
                        str(entry.get("target", "")),
                        str(entry.get("outcome", "")),
                        key,
                        json.dumps(entry),
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def history(self, limit: int = 100,
                before_ts: Optional[float] = None) -> List[Dict]:
        """Newest-first page of history; pass before_ts to page backwards."""
        q = "SELECT raw FROM history"
        args: list = []
        if before_ts is not None:
            q += " WHERE ts < ?"
            args.append(before_ts)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [json.loads(r[0]) for r in rows]

    # -- metric samples -----------------------------------------------------

    def record_sample(self, metric: str, value: float,
                      ts: Optional[float] = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO metric_samples (ts, metric, value)"
                " VALUES (?, ?, ?)",
                (ts if ts is not None else time.time(), metric, float(value)),
            )
            self._conn.commit()

    def samples(self, metric: str, since: float) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, value FROM metric_samples"
                " WHERE metric = ? AND ts >= ? ORDER BY ts",
                (metric, since),
            ).fetchall()
        return [{"ts": r[0], "value": r[1]} for r in rows]

    def metrics(self) -> List[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT metric FROM metric_samples").fetchall()
        return [r[0] for r in rows]

    # -- events ---------------------------------------------------------------

    def record_event(self, kind: str, detail: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (ts, kind, detail) VALUES (?, ?, ?)",
                (time.time(), str(kind), str(detail)),
            )
            self._conn.commit()

    def events(self, limit: int = 100) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, kind, detail FROM events"
                " ORDER BY ts DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [{"ts": r[0], "kind": r[1], "detail": r[2]} for r in rows]

    # -- retention ------------------------------------------------------------

    def prune(self, keep_days: int = 90) -> None:
        """Drop old samples/events. History is never pruned (unbounded)."""
        cutoff = time.time() - keep_days * 86400
        with self._lock:
            self._conn.execute(
                "DELETE FROM metric_samples WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self._conn.commit()
