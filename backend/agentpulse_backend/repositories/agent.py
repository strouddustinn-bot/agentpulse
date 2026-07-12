"""Agent repository — enrollment, credential management, and agent lookups."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from typing import Any, Dict, List, Optional

from ..database.connection import Connection, DatabaseError, Store, utc_now_iso


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class AgentRepository:
    """Data access for agents and their credentials."""

    def __init__(self, store: Store) -> None:
        self.store = store

    # ── Enrollment token operations ───────────────────────────────────────────

    def create_enrollment_token(
        self,
        *,
        ttl_seconds: int = 300,
        tenant_id: str = "default",
    ) -> tuple[str, str]:
        """Create a one-time enrollment token.

        Returns (plaintext_token, token_hash).
        The plaintext token is returned ONLY here — store it and give it to the agent.
        """
        plaintext = secrets.token_urlsafe(32)
        token_hash = _hash_secret(plaintext)
        token_id = str(uuid.uuid4())
        now = utc_now_iso()
        expires_at = _offset_seconds_from_now(ttl_seconds)

        with self.store.transaction() as conn:
            conn.execute(
                """INSERT INTO enrollment_tokens
                   (id, tenant_id, token_hash, created_by_cred_id, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (token_id, tenant_id, token_hash, "", now, expires_at),
            )
        return plaintext, token_hash

    def consume_enrollment_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Atomically consume an enrollment token if it is valid and unused.

        Returns tenant_id on success, None if invalid or already consumed.
        """
        token_hash = _hash_secret(token)
        now = utc_now_iso()
        with self.store.transaction() as conn:
            row = conn.query_one(
                """SELECT id, tenant_id, expires_at, consumed_at
                   FROM enrollment_tokens
                   WHERE token_hash = ?""",
                (token_hash,),
            )
            if row is None:
                return None
            if row["consumed_at"] is not None:
                return None
            if row["expires_at"] < now:
                return None
            conn.execute(
                """UPDATE enrollment_tokens
                   SET consumed_at = ?
                   WHERE id = ? AND consumed_at IS NULL""",
                (now, row["id"]),
            )
            # Verify the update took (token wasn't consumed between our read and update)
            updated = conn.query_one(
                "SELECT consumed_at FROM enrollment_tokens WHERE id = ?",
                (row["id"],),
            )
            if updated is None or updated["consumed_at"] is None:
                return None
            return {"tenant_id": row["tenant_id"], "token_id": row["id"]}

    # ── Agent CRUD ──────────────────────────────────────────────────────────

    def create_agent(
        self,
        *,
        hostname: str,
        os: str,
        architecture: str,
        agent_version: str,
        config_version: str = "",
        machine_id: str = "",
        checks_offered: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        tenant_id: str = "default",
    ) -> tuple[str, str]:
        """Create a new agent and issue its first credential.

        Returns (agent_id, plaintext_credential).
        The plaintext credential is returned ONLY here — give it to the agent once.
        """
        agent_id = str(uuid.uuid4())
        credential = "ap_" + secrets.token_urlsafe(32)
        credential_hash = _hash_secret(credential)
        credential_prefix = credential[:12]
        now = utc_now_iso()

        with self.store.transaction() as conn:
            conn.execute(
                """INSERT INTO agents
                   (id, tenant_id, hostname, os, architecture, agent_version,
                    config_version, machine_id, status, enrolled_at, last_seen_at,
                    policy_id, tags, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_id, tenant_id, hostname, os, architecture,
                    agent_version, config_version, machine_id, "online",
                    now, now, "", json.dumps(tags or []),
                    now, now,
                ),
            )
            conn.execute(
                """INSERT INTO agent_credentials
                   (id, agent_id, credential_hash, credential_prefix, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), agent_id, credential_hash, credential_prefix, now),
            )
        return agent_id, credential

    def get_agent(self, agent_id: str, tenant_id: str = "default") -> Optional[Dict[str, Any]]:
        """Return an agent by ID, or None."""
        row = self.store.connection.query_one(
            """SELECT id, tenant_id, hostname, os, architecture,
                      agent_version, config_version, machine_id, status,
                      enrolled_at, last_seen_at, policy_id, tags
               FROM agents WHERE id = ? AND tenant_id = ?""",
            (agent_id, tenant_id),
        )
        if row is None:
            return None
        return _parse_agent_row(row)

    def list_agents(self, tenant_id: str = "default") -> List[Dict[str, Any]]:
        """Return all agents for a tenant."""
        rows = self.store.connection.query(
            """SELECT id, tenant_id, hostname, os, architecture,
                      agent_version, config_version, machine_id, status,
                      enrolled_at, last_seen_at, policy_id, tags
               FROM agents WHERE tenant_id = ?
               ORDER BY last_seen_at DESC""",
            (tenant_id,),
        )
        return [_parse_agent_row(r) for r in rows]

    def update_last_seen(self, agent_id: str, tenant_id: str = "default") -> None:
        """Update the last_seen_at timestamp to now."""
        now = utc_now_iso()
        with self.store.transaction() as conn:
            conn.execute(
                "UPDATE agents SET last_seen_at = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                (now, now, agent_id, tenant_id),
            )

    def authenticate_agent(self, credential: str) -> Optional[Dict[str, Any]]:
        """Look up an agent by credential hash. Returns agent dict or None."""
        if not credential:
            return None
        credential_hash = _hash_secret(credential)
        row = self.store.connection.query_one(
            """SELECT c.agent_id, c.credential_hash,
                      a.tenant_id, a.status, a.agent_version
               FROM agent_credentials c
               JOIN agents a ON a.id = c.agent_id
               WHERE c.credential_hash = ?
                 AND c.revoked_at IS NULL
                 AND (c.expires_at IS NULL OR c.expires_at > ?)""",
            (credential_hash, utc_now_iso()),
        )
        if row is None:
            return None
        if not hmac.compare_digest(row["credential_hash"], credential_hash):
            return None
        return {"agent_id": row["agent_id"], "tenant_id": row["tenant_id"], "status": row["status"]}

    def update_agent_status(self, agent_id: str, status: str) -> None:
        now = utc_now_iso()
        with self.store.transaction() as conn:
            conn.execute(
                "UPDATE agents SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, agent_id),
            )


def _parse_agent_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw agent row into a clean dict."""
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "hostname": row["hostname"],
        "os": row["os"],
        "architecture": row["architecture"],
        "agent_version": row["agent_version"],
        "config_version": row["config_version"],
        "machine_id": row["machine_id"],
        "status": row["status"],
        "enrolled_at": row["enrolled_at"],
        "last_seen_at": row["last_seen_at"],
        "policy_id": row["policy_id"],
        "tags": json.loads(row["tags"]) if row["tags"] else [],
    }


def _offset_seconds_from_now(seconds: int) -> str:
    """Return an ISO-8601 timestamp `seconds` in the future."""
    from datetime import datetime, timezone, timedelta
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
