"""Incident repository — lifecycle management for incidents and incident events."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from ..database.connection import Store, utc_now_iso


class IncidentRepository:
    def __init__(self, store: Store) -> None:
        self.store = store

    # ── Core CRUD ──────────────────────────────────────────────────────────────

    def create_incident(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        check_id: str,
        check_type: str,
        severity: str,
        title: str,
        body: str = "",
        evidence: Optional[List[str]] = None,
        policy_id: str = "",
        is_baseline_anomaly: bool = False,
        tags: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a new open incident and its opening event atomically."""
        incident_id = str(uuid.uuid4())
        now = utc_now_iso()
        evidence_json = json.dumps(evidence or [])
        tags_json = json.dumps(tags or [])

        with self.store.transaction() as conn:
            conn.execute(
                """INSERT INTO incidents
                   (id, tenant_id, agent_id, check_id, check_type, status, severity,
                    title, body, evidence, opened_at, policy_id,
                    is_baseline_anomaly, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    incident_id, tenant_id, agent_id, check_id, check_type,
                    "open", severity, title, body, evidence_json, now,
                    policy_id, int(is_baseline_anomaly), tags_json,
                ),
            )
            conn.execute(
                """INSERT INTO incident_events
                   (incident_id, event_type, actor, body, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    incident_id, "incident_opened", "agent",
                    json.dumps({"reason": "check_failed", "severity": severity}),
                    now,
                ),
            )

        return self.get_incident(incident_id, tenant_id)

    def get_incident(
        self, incident_id: str, tenant_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        row = self.store.connection.query_one(
            """SELECT id, tenant_id, agent_id, check_id, check_type, status,
                      severity, title, body, evidence, opened_at,
                      acknowledged_at, acknowledged_by, resolved_at, resolved_by,
                      remediation_id, policy_id, is_baseline_anomaly, tags
               FROM incidents WHERE id = ? AND tenant_id = ?""",
            (incident_id, tenant_id),
        )
        if row is None:
            return None
        return _parse_incident_row(row)

    def list_incidents(
        self,
        tenant_id: str = "default",
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        conditions = ["tenant_id = ?"]
        params: List[Any] = [tenant_id]
        if status:
            conditions.append("status = ?")
            params.append(status)
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        where = " AND ".join(conditions)
        safe_limit = max(1, min(limit, 200))
        params.append(safe_limit)

        rows = self.store.connection.query(
            f"""SELECT id, tenant_id, agent_id, check_id, check_type, status,
                        severity, title, body, evidence, opened_at,
                        acknowledged_at, acknowledged_by, resolved_at, resolved_by,
                        remediation_id, policy_id, is_baseline_anomaly, tags
                 FROM incidents
                 WHERE {where}
                 ORDER BY opened_at DESC
                 LIMIT ?""",
            tuple(params),
        )
        return [_parse_incident_row(r) for r in rows]

    def add_incident_evidence(
        self,
        incident_id: str,
        evidence: List[str],
        tenant_id: str = "default",
    ) -> None:
        """Append evidence to an existing open incident."""
        now = utc_now_iso()
        with self.store.transaction() as conn:
            row = conn.query_one(
                "SELECT evidence FROM incidents WHERE id = ? AND tenant_id = ?",
                (incident_id, tenant_id),
            )
            if row is None:
                return
            existing = json.loads(row["evidence"] or "[]")
            combined = existing + evidence
            conn.execute(
                "UPDATE incidents SET evidence = ? WHERE id = ?",
                (json.dumps(combined), incident_id),
            )
            conn.execute(
                """INSERT INTO incident_events
                   (incident_id, event_type, actor, body, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    incident_id, "evidence_appended", "agent",
                    json.dumps({"added": evidence}),
                    now,
                ),
            )

    def acknowledge_incident(
        self,
        incident_id: str,
        acknowledged_by: str = "operator",
        note: str = "",
        tenant_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        now = utc_now_iso()
        with self.store.transaction() as conn:
            conn.execute(
                """UPDATE incidents
                   SET status = 'acknowledged',
                       acknowledged_at = ?,
                       acknowledged_by = ?
                   WHERE id = ? AND tenant_id = ? AND status = 'open'""",
                (now, acknowledged_by, incident_id, tenant_id),
            )
            conn.execute(
                """INSERT INTO incident_events
                   (incident_id, event_type, actor, actor_id, body, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    incident_id, "incident_acknowledged", "operator",
                    acknowledged_by, json.dumps({"note": note}), now,
                ),
            )
        return self.get_incident(incident_id, tenant_id)

    def resolve_incident(
        self,
        incident_id: str,
        resolved_by: str = "agent",
        note: str = "",
        tenant_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        now = utc_now_iso()
        with self.store.transaction() as conn:
            conn.execute(
                """UPDATE incidents
                   SET status = 'resolved', resolved_at = ?, resolved_by = ?
                   WHERE id = ? AND tenant_id = ?
                     AND status IN ('open', 'acknowledged')""",
                (now, resolved_by, incident_id, tenant_id),
            )
            conn.execute(
                """INSERT INTO incident_events
                   (incident_id, event_type, actor, actor_id, body, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    incident_id, "incident_resolved", resolved_by,
                    "", json.dumps({"note": note}), now,
                ),
            )
        return self.get_incident(incident_id, tenant_id)

    def suppress_incident(
        self,
        incident_id: str,
        tenant_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        now = utc_now_iso()
        with self.store.transaction() as conn:
            conn.execute(
                """UPDATE incidents
                   SET status = 'suppressed'
                   WHERE id = ? AND tenant_id = ? AND status = 'open'""",
                (incident_id, tenant_id),
            )
            conn.execute(
                """INSERT INTO incident_events
                   (incident_id, event_type, actor, body, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    incident_id, "incident_suppressed", "agent",
                    json.dumps({"reason": "cooldown"}), now,
                ),
            )
        return self.get_incident(incident_id, tenant_id)

    def get_incident_events(
        self,
        incident_id: str,
        tenant_id: str = "default",
    ) -> List[Dict[str, Any]]:
        rows = self.store.connection.query(
            """SELECT id, incident_id, event_type, actor, actor_id, body, created_at
               FROM incident_events
               WHERE incident_id = ?
               ORDER BY created_at ASC""",
            (incident_id,),
        )
        return [dict(r) for r in rows]

    # ── Incident + check result integration ────────────────────────────────────

    def upsert_incident_from_check_result(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        check_id: str,
        check_type: str,
        severity: str,
        title: str,
        evidence: Optional[List[str]] = None,
        policy_id: str = "",
    ) -> tuple[Dict[str, Any], bool]:
        """Create a new incident, or add evidence to an existing open one for the same check.

        Returns (incident, is_new).
        This is the core deduplication logic: one open incident per check at a time.
        """
        row = self.store.connection.query_one(
            "SELECT id FROM incidents WHERE agent_id = ? AND check_id = ? AND status = 'open'",
            (agent_id, check_id),
        )
        if row is not None:
            inc = self.get_incident(row["id"], tenant_id)
            if inc is not None:
                self.add_incident_evidence(inc["id"], evidence or [], tenant_id)
                return inc, False

        incident = self.create_incident(
            tenant_id=tenant_id,
            agent_id=agent_id,
            check_id=check_id,
            check_type=check_type,
            severity=severity,
            title=title,
            evidence=evidence,
            policy_id=policy_id,
        )
        if incident is None:
            raise RuntimeError("create_incident returned None unexpectedly")
        return incident, True

    def resolve_incidents_for_check(
        self,
        agent_id: str,
        check_id: str,
        resolved_by: str = "agent",
        note: str = "",
        tenant_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """Resolve all open incidents for a given check on a given agent.

        Used when a check recovers — all related open incidents are closed.
        """
        resolved = []
        rows = self.store.connection.query(
            """SELECT id FROM incidents
               WHERE agent_id = ? AND check_id = ? AND status IN ('open', 'acknowledged')
                 AND tenant_id = ?""",
            (agent_id, check_id, tenant_id),
        )
        for row in rows:
            inc = self.resolve_incident(row["id"], resolved_by, note, tenant_id)
            if inc:
                resolved.append(inc)
        return resolved


def _parse_incident_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "agent_id": row["agent_id"],
        "check_id": row["check_id"],
        "check_type": row["check_type"],
        "status": row["status"],
        "severity": row["severity"],
        "title": row["title"],
        "body": row["body"],
        "evidence": json.loads(row["evidence"]) if row["evidence"] else [],
        "opened_at": row["opened_at"],
        "acknowledged_at": row["acknowledged_at"],
        "acknowledged_by": row["acknowledged_by"],
        "resolved_at": row["resolved_at"],
        "resolved_by": row["resolved_by"],
        "remediation_id": row["remediation_id"],
        "policy_id": row["policy_id"],
        "is_baseline_anomaly": bool(row["is_baseline_anomaly"]),
        "tags": json.loads(row["tags"]) if row["tags"] else [],
    }
