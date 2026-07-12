"""Audit event repository — append-only log of all important state transitions."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..database.connection import Store, utc_now_iso


class AuditRepository:
    """Append-only audit log. Records why things happened, not just that they did."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def record(
        self,
        *,
        component: str,
        event_type: str,
        actor: str = "",
        agent_id: Optional[str] = None,
        incident_id: Optional[str] = None,
        remediation_id: Optional[str] = None,
        outcome: str,
        body: Optional[Dict[str, Any]] = None,
        tenant_id: str = "default",
    ) -> int:
        """Append an audit event. Returns the event ID."""
        now = utc_now_iso()
        body_json = json.dumps(body or {})
        with self.store.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO audit_events
                   (tenant_id, timestamp, component, event_type, actor,
                    agent_id, incident_id, remediation_id, outcome, body)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tenant_id, now, component, event_type, actor,
                    agent_id, incident_id, remediation_id, outcome, body_json,
                ),
            )
            return int(cur.lastrowid or 0)

    def list(
        self,
        tenant_id: str = "default",
        agent_id: Optional[str] = None,
        incident_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        conditions = ["tenant_id = ?"]
        params: List[Any] = [tenant_id]
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if incident_id:
            conditions.append("incident_id = ?")
            params.append(incident_id)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        where = " AND ".join(conditions)
        safe_limit = max(1, min(limit, 500))
        params.append(safe_limit)

        rows = self.store.connection.query(
            f"""SELECT id, tenant_id, timestamp, component, event_type, actor,
                        agent_id, incident_id, remediation_id, outcome, body
                 FROM audit_events
                 WHERE {where}
                 ORDER BY timestamp DESC
                 LIMIT ?""",
            tuple(params),
        )
        return [_parse_row(r) for r in rows]

    def list_for_agent(
        self,
        agent_id: str,
        tenant_id: str = "default",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self.list(tenant_id=tenant_id, agent_id=agent_id, limit=limit)

    def list_for_incident(
        self,
        incident_id: str,
        tenant_id: str = "default",
    ) -> List[Dict[str, Any]]:
        return self.list(tenant_id=tenant_id, incident_id=incident_id, limit=200)


def _parse_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "timestamp": row["timestamp"],
        "component": row["component"],
        "event_type": row["event_type"],
        "actor": row["actor"],
        "agent_id": row["agent_id"],
        "incident_id": row["incident_id"],
        "remediation_id": row["remediation_id"],
        "outcome": row["outcome"],
        "body": json.loads(row["body"]) if row["body"] else {},
    }
