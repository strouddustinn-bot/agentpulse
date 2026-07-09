"""SQLite persistence for the AgentPulse backend.

The backend deliberately starts with stdlib sqlite3 so it is easy to run locally
and cheap to deploy. The schema keeps an explicit org_id on every row so the
same API can be migrated to Postgres/multi-tenant hosting later without changing
agent payloads.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_ORG_ID = "default"


class StoreError(RuntimeError):
    """Raised for backend persistence or validation failures."""


@dataclass
class Principal:
    org_id: str
    token_id: int
    label: str


@dataclass
class LicenseCheck:
    active: bool
    reason: str
    org_id: str = DEFAULT_ORG_ID
    plan: str = "unknown"
    max_agents: int = 0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        path = Path(self.db_path)
        if path.parent and str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with closing(self.connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agents (
                    org_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    hostname TEXT NOT NULL,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_payload_json TEXT NOT NULL,
                    PRIMARY KEY (org_id, agent_id)
                );

                CREATE TABLE IF NOT EXISTS checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    hostname TEXT NOT NULL,
                    status TEXT NOT NULL,
                    observations INTEGER NOT NULL DEFAULT 0,
                    breaches INTEGER NOT NULL DEFAULT 0,
                    actions INTEGER NOT NULL DEFAULT 0,
                    queued INTEGER NOT NULL DEFAULT 0,
                    alerts INTEGER NOT NULL DEFAULT 0,
                    anomalies INTEGER NOT NULL DEFAULT 0,
                    escalations INTEGER NOT NULL DEFAULT 0,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    errors INTEGER NOT NULL DEFAULT 0,
                    version TEXT NOT NULL,
                    agent_timestamp TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_checkins_agent_received
                    ON checkins(org_id, agent_id, received_at DESC);

                CREATE TABLE IF NOT EXISTS licenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id TEXT NOT NULL,
                    license_hash TEXT NOT NULL UNIQUE,
                    plan TEXT NOT NULL,
                    status TEXT NOT NULL,
                    max_agents INTEGER NOT NULL,
                    expires_at TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def create_api_key(
        self, *, org_id: str = DEFAULT_ORG_ID, label: str = "default"
    ) -> str:
        token = "ap_" + secrets.token_urlsafe(32)
        with closing(self.connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO api_keys (org_id, label, token_hash, active, created_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (org_id, label, hash_secret(token), utc_now_iso()),
            )
        return token

    def authenticate_api_key(self, token: str) -> Optional[Principal]:
        if not token:
            return None
        token_hash = hash_secret(token)
        with closing(self.connect()) as conn, conn:
            row = conn.execute(
                """
                SELECT id, org_id, label, token_hash
                FROM api_keys
                WHERE token_hash = ? AND active = 1
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        if not hmac.compare_digest(row["token_hash"], token_hash):
            return None
        return Principal(
            org_id=row["org_id"], token_id=int(row["id"]), label=row["label"]
        )

    def record_checkin(self, *, org_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = normalize_checkin_payload(payload)
        received_at = utc_now_iso()
        payload_json = json.dumps(normalized, sort_keys=True)
        with closing(self.connect()) as conn, conn:
            existing = conn.execute(
                "SELECT first_seen_at FROM agents WHERE org_id = ? AND agent_id = ?",
                (org_id, normalized["agent_id"]),
            ).fetchone()
            first_seen_at = existing["first_seen_at"] if existing else received_at
            conn.execute(
                """
                INSERT INTO agents (
                    org_id, agent_id, hostname, version, status,
                    first_seen_at, last_seen_at, last_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(org_id, agent_id) DO UPDATE SET
                    hostname = excluded.hostname,
                    version = excluded.version,
                    status = excluded.status,
                    last_seen_at = excluded.last_seen_at,
                    last_payload_json = excluded.last_payload_json
                """,
                (
                    org_id,
                    normalized["agent_id"],
                    normalized["hostname"],
                    normalized["version"],
                    normalized["status"],
                    first_seen_at,
                    received_at,
                    payload_json,
                ),
            )
            cur = conn.execute(
                """
                INSERT INTO checkins (
                    org_id, agent_id, hostname, status, observations, breaches,
                    actions, queued, alerts, anomalies, escalations, blocked,
                    errors, version, agent_timestamp, received_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    org_id,
                    normalized["agent_id"],
                    normalized["hostname"],
                    normalized["status"],
                    normalized["observations"],
                    normalized["breaches"],
                    normalized["actions"],
                    normalized["queued"],
                    normalized["alerts"],
                    normalized["anomalies"],
                    normalized["escalations"],
                    normalized["blocked"],
                    normalized["errors"],
                    normalized["version"],
                    normalized["timestamp"],
                    received_at,
                    payload_json,
                ),
            )
        return {
            "checkin_id": int(cur.lastrowid),
            "agent_id": normalized["agent_id"],
            "status": normalized["status"],
            "received_at": received_at,
        }

    def list_agents(self, *, org_id: str) -> List[Dict[str, Any]]:
        with closing(self.connect()) as conn, conn:
            rows = conn.execute(
                """
                SELECT agent_id, hostname, version, status, first_seen_at, last_seen_at
                FROM agents
                WHERE org_id = ?
                ORDER BY last_seen_at DESC
                """,
                (org_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_checkins(
        self, *, org_id: str, agent_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with closing(self.connect()) as conn, conn:
            rows = conn.execute(
                """
                SELECT id, agent_id, hostname, status, observations, breaches,
                       actions, queued, alerts, anomalies, escalations, blocked,
                       errors, version, agent_timestamp, received_at
                FROM checkins
                WHERE org_id = ? AND agent_id = ?
                ORDER BY received_at DESC
                LIMIT ?
                """,
                (org_id, agent_id, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_license(
        self,
        *,
        org_id: str = DEFAULT_ORG_ID,
        plan: str = "starter",
        max_agents: int = 1,
        expires_at: Optional[str] = None,
    ) -> str:
        license_key = "apl_" + secrets.token_urlsafe(32)
        with closing(self.connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO licenses (
                    org_id, license_hash, plan, status, max_agents, expires_at, created_at
                ) VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    org_id,
                    hash_secret(license_key),
                    plan,
                    int(max_agents),
                    expires_at,
                    utc_now_iso(),
                ),
            )
        return license_key

    def verify_license(self, *, license_key: str, agent_id: str = "") -> LicenseCheck:
        if not license_key:
            return LicenseCheck(active=False, reason="missing license key")
        license_hash = hash_secret(license_key)
        with closing(self.connect()) as conn, conn:
            row = conn.execute(
                """
                SELECT org_id, plan, status, max_agents, expires_at, license_hash
                FROM licenses
                WHERE license_hash = ?
                """,
                (license_hash,),
            ).fetchone()
            if row is None or not hmac.compare_digest(
                row["license_hash"], license_hash
            ):
                return LicenseCheck(active=False, reason="license not found")
            if row["status"] != "active":
                return LicenseCheck(
                    active=False,
                    reason=f"license is {row['status']}",
                    org_id=row["org_id"],
                    plan=row["plan"],
                    max_agents=int(row["max_agents"]),
                )
            if row["expires_at"] and row["expires_at"] < utc_now_iso():
                return LicenseCheck(
                    active=False,
                    reason="license expired",
                    org_id=row["org_id"],
                    plan=row["plan"],
                    max_agents=int(row["max_agents"]),
                )
            if agent_id:
                count = conn.execute(
                    "SELECT COUNT(*) AS n FROM agents WHERE org_id = ?",
                    (row["org_id"],),
                ).fetchone()["n"]
                known = conn.execute(
                    "SELECT 1 FROM agents WHERE org_id = ? AND agent_id = ?",
                    (row["org_id"], agent_id),
                ).fetchone()
                if known is None and int(count) >= int(row["max_agents"]):
                    return LicenseCheck(
                        active=False,
                        reason="agent limit reached",
                        org_id=row["org_id"],
                        plan=row["plan"],
                        max_agents=int(row["max_agents"]),
                    )
        return LicenseCheck(
            active=True,
            reason="ok",
            org_id=row["org_id"],
            plan=row["plan"],
            max_agents=int(row["max_agents"]),
        )


def _required_str(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise StoreError(f"check-in field {key!r} must be a non-empty string")
    return value.strip()


def _count(payload: Dict[str, Any], key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StoreError(f"check-in field {key!r} must be a non-negative integer")
    return int(value)


def normalize_checkin_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise StoreError("check-in payload must be a JSON object")
    status = _required_str(payload, "status")
    if status not in ("ok", "attention", "error"):
        raise StoreError("check-in field 'status' must be ok, attention, or error")
    normalized = {
        "agent_id": _required_str(payload, "agent_id"),
        "hostname": _required_str(payload, "hostname"),
        "status": status,
        "observations": _count(payload, "observations"),
        "breaches": _count(payload, "breaches"),
        "actions": _count(payload, "actions"),
        "queued": _count(payload, "queued"),
        "alerts": _count(payload, "alerts"),
        "anomalies": _count(payload, "anomalies"),
        "escalations": _count(payload, "escalations"),
        "blocked": _count(payload, "blocked"),
        "errors": _count(payload, "errors"),
        "timestamp": _required_str(payload, "timestamp"),
        "version": _required_str(payload, "version"),
    }
    return normalized
