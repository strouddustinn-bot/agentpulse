"""SQLite persistence for the dashboard service.

Tables:
  history        — mirror of agent history, unbounded (agent caps at 200)
  metric_samples — host metric time series for charts
  events         — service-level event log (ingest errors, UI actions)
  fleet_agents   — latest authenticated heartbeat for each remote agent

Stdlib sqlite3, WAL mode, no ORM. All statements are parameterized. A single
threading.Lock serializes access because the connection is shared between the
background ingest thread and request handlers.
"""

from __future__ import annotations

import hashlib
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

CREATE TABLE IF NOT EXISTS fleet_agents (
    agent_id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    last_seen REAL NOT NULL,
    state TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fleet_last_seen ON fleet_agents(last_seen);

CREATE TABLE IF NOT EXISTS billing_customers (
    stripe_customer_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    stripe_subscription_id TEXT PRIMARY KEY,
    stripe_customer_id TEXT NOT NULL,
    status TEXT NOT NULL,
    price_id TEXT NOT NULL,
    plan TEXT NOT NULL,
    server_limit INTEGER NOT NULL,
    current_period_end INTEGER,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_customer
    ON subscriptions(stripe_customer_id, updated_at);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stripe_customer_id TEXT NOT NULL,
    key_hash TEXT UNIQUE NOT NULL,
    key_prefix TEXT NOT NULL,
    created_at REAL NOT NULL,
    revoked_at REAL
);
CREATE INDEX IF NOT EXISTS idx_api_keys_customer ON api_keys(stripe_customer_id);

CREATE TABLE IF NOT EXISTS licensed_agents (
    stripe_customer_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    PRIMARY KEY (stripe_customer_id, agent_id)
);

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    processed_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS onboarding_claims (
    checkout_session_id TEXT PRIMARY KEY,
    stripe_customer_id TEXT NOT NULL,
    claimed_at REAL NOT NULL
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

    # -- fleet heartbeats -----------------------------------------------------

    def upsert_agent(self, agent_id: str, hostname: str,
                     state: Dict[str, Any]) -> None:
        """Persist the latest heartbeat for one authenticated remote agent."""
        now = time.time()
        raw = json.dumps(state)
        with self._lock:
            self._conn.execute(
                "INSERT INTO fleet_agents (agent_id, hostname, last_seen, state)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(agent_id) DO UPDATE SET"
                " hostname=excluded.hostname, last_seen=excluded.last_seen,"
                " state=excluded.state",
                (agent_id, hostname, now, raw),
            )
            self._conn.commit()

    def fleet_agents(self, stale_after: float = 600.0) -> Dict[str, Dict]:
        """Return latest remote state keyed by agent id, including staleness."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT agent_id, hostname, last_seen, state"
                " FROM fleet_agents ORDER BY agent_id"
            ).fetchall()
        now = time.time()
        return {
            row[0]: {
                "agent_id": row[0],
                "hostname": row[1],
                "last_seen": row[2],
                "state": json.loads(row[3]),
                "stale": (now - row[2]) > stale_after,
            }
            for row in rows
        }

    # -- Stripe billing and entitlements -------------------------------------

    @staticmethod
    def _api_key_hash(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def upsert_billing_customer(self, stripe_customer_id: str, email: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO billing_customers"
                " (stripe_customer_id, email, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(stripe_customer_id) DO UPDATE SET"
                " email=excluded.email, updated_at=excluded.updated_at",
                (stripe_customer_id, email.strip().lower(), now, now),
            )
            self._conn.commit()

    def upsert_subscription(self, stripe_subscription_id: str,
                            stripe_customer_id: str, status: str,
                            price_id: str, plan: str, server_limit: int,
                            current_period_end: Optional[int]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO subscriptions"
                " (stripe_subscription_id, stripe_customer_id, status, price_id,"
                " plan, server_limit, current_period_end, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(stripe_subscription_id) DO UPDATE SET"
                " stripe_customer_id=excluded.stripe_customer_id,"
                " status=excluded.status, price_id=excluded.price_id,"
                " plan=excluded.plan, server_limit=excluded.server_limit,"
                " current_period_end=excluded.current_period_end,"
                " updated_at=excluded.updated_at",
                (stripe_subscription_id, stripe_customer_id, status, price_id,
                 plan, int(server_limit), current_period_end, time.time()),
            )
            self._conn.commit()

    def subscription_for_customer(self, stripe_customer_id: str) -> Optional[Dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT stripe_subscription_id, status, price_id, plan,"
                " server_limit, current_period_end, updated_at"
                " FROM subscriptions WHERE stripe_customer_id = ?"
                " ORDER BY updated_at DESC LIMIT 1",
                (stripe_customer_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "stripe_subscription_id": row[0], "status": row[1],
            "price_id": row[2], "plan": row[3], "server_limit": row[4],
            "current_period_end": row[5], "updated_at": row[6],
        }

    def issue_api_key(self, stripe_customer_id: str, raw_key: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO api_keys"
                " (stripe_customer_id, key_hash, key_prefix, created_at)"
                " VALUES (?, ?, ?, ?)",
                (stripe_customer_id, self._api_key_hash(raw_key), raw_key[:12],
                 time.time()),
            )
            self._conn.commit()

    def claim_and_issue_api_key(self, checkout_session_id: str,
                                stripe_customer_id: str, raw_key: str) -> bool:
        """Atomically claim a Checkout Session and persist a hashed API key."""
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                self._conn.execute(
                    "INSERT INTO onboarding_claims"
                    " (checkout_session_id, stripe_customer_id, claimed_at)"
                    " VALUES (?, ?, ?)",
                    (checkout_session_id, stripe_customer_id, time.time()),
                )
                self._conn.execute(
                    "INSERT INTO api_keys"
                    " (stripe_customer_id, key_hash, key_prefix, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (stripe_customer_id, self._api_key_hash(raw_key), raw_key[:12],
                     time.time()),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                self._conn.rollback()
                return False

    def _account_for_key_locked(self, raw_key: str) -> Optional[Dict]:
        row = self._conn.execute(
            "SELECT k.stripe_customer_id, c.email, s.status, s.plan,"
            " s.server_limit, s.stripe_subscription_id"
            " FROM api_keys k"
            " JOIN billing_customers c"
            "   ON c.stripe_customer_id = k.stripe_customer_id"
            " LEFT JOIN subscriptions s"
            "   ON s.stripe_customer_id = k.stripe_customer_id"
            " WHERE k.key_hash = ? AND k.revoked_at IS NULL"
            " ORDER BY s.updated_at DESC LIMIT 1",
            (self._api_key_hash(raw_key),),
        ).fetchone()
        if row is None:
            return None
        return {
            "stripe_customer_id": row[0], "email": row[1],
            "status": row[2], "plan": row[3], "server_limit": row[4],
            "stripe_subscription_id": row[5],
        }

    def customer_for_api_key(self, raw_key: str) -> Optional[Dict]:
        with self._lock:
            return self._account_for_key_locked(raw_key)

    def authorize_agent(self, raw_key: str, agent_id: str) -> Dict:
        """Authenticate a license key and atomically enforce its server limit."""
        with self._lock:
            account = self._account_for_key_locked(raw_key)
            if account is None:
                return {"allowed": False, "reason": "invalid_api_key"}
            if account["status"] not in ("active", "trialing"):
                return {"allowed": False, "reason": "subscription_inactive"}
            customer_id = account["stripe_customer_id"]
            existing = self._conn.execute(
                "SELECT 1 FROM licensed_agents"
                " WHERE stripe_customer_id = ? AND agent_id = ?",
                (customer_id, agent_id),
            ).fetchone()
            count = self._conn.execute(
                "SELECT COUNT(*) FROM licensed_agents"
                " WHERE stripe_customer_id = ?", (customer_id,)
            ).fetchone()[0]
            limit = int(account["server_limit"] or 0)
            if existing is None and count >= limit:
                return {"allowed": False, "reason": "server_limit_exceeded",
                        **account}
            now = time.time()
            self._conn.execute(
                "INSERT INTO licensed_agents"
                " (stripe_customer_id, agent_id, first_seen, last_seen)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(stripe_customer_id, agent_id) DO UPDATE SET"
                " last_seen=excluded.last_seen",
                (customer_id, agent_id, now, now),
            )
            self._conn.commit()
            return {"allowed": True, "reason": "ok", **account}

    def webhook_seen(self, event_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM stripe_webhook_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return row is not None

    def record_webhook(self, event_id: str, event_type: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO stripe_webhook_events"
                " (event_id, event_type, processed_at) VALUES (?, ?, ?)",
                (event_id, event_type, time.time()),
            )
            self._conn.commit()

    # -- retention ------------------------------------------------------------

    def prune(self, keep_days: int = 90) -> None:
        """Drop old samples/events. History is never pruned (unbounded)."""
        cutoff = time.time() - keep_days * 86400
        with self._lock:
            self._conn.execute(
                "DELETE FROM metric_samples WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self._conn.commit()
