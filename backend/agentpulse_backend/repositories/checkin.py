"""Check-in repository — idempotent check-in persistence and result storage."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from ..database.connection import Store, utc_now_iso


class CheckinRepository:
    def __init__(self, store: Store) -> None:
        self.store = store

    def record_checkin(
        self,
        *,
        agent_id: str,
        idempotency_key: str,
        sequence: int,
        agent_timestamp: str,
        hostname: str,
        agent_version: str,
        config_version: str,
        status: str,
        uptime_seconds: int,
        observations: int,
        breaches: int,
        alerts: int,
        anomalies: int,
        escalations: int,
        blocked: int,
        errors: int,
        offline_queue_depth: int,
        check_results: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[int, bool]:
        """Insert a check-in, or return the existing ID if the idempotency key matches.

        Returns (checkin_id, is_duplicate).
        If is_duplicate is True, the check-in already existed and was not re-inserted.
        """
        now = utc_now_iso()
        payload = {
            "agent_id": agent_id,
            "hostname": hostname,
            "agent_version": agent_version,
            "config_version": config_version,
            "status": status,
            "uptime_seconds": uptime_seconds,
            "observations": observations,
            "breaches": breaches,
            "alerts": alerts,
            "anomalies": anomalies,
            "escalations": escalations,
            "blocked": blocked,
            "errors": errors,
            "offline_queue_depth": offline_queue_depth,
            "sequence": sequence,
        }
        payload_json = json.dumps(payload, sort_keys=True)

        with self.store.transaction() as conn:
            # Check for existing idempotency key
            existing = conn.query_one(
                "SELECT id FROM check_ins WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            if existing is not None:
                return int(existing["id"]), True

            cur = conn.execute(
                """INSERT INTO check_ins
                   (agent_id, idempotency_key, sequence, agent_timestamp, received_at,
                    hostname, agent_version, config_version, status, uptime_seconds,
                    observations, breaches, alerts, anomalies, escalations,
                    blocked, errors, offline_queue_depth, payload_json, is_duplicate)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    agent_id, idempotency_key, sequence, agent_timestamp, now,
                    hostname, agent_version, config_version, status, uptime_seconds,
                    observations, breaches, alerts, anomalies, escalations,
                    blocked, errors, offline_queue_depth, payload_json,
                ),
            )
            checkin_id = int(cur.lastrowid or 0)

            # Insert per-check results
            if check_results:
                self._insert_results(conn, checkin_id, check_results)

        return checkin_id, False

    def _insert_results(
        self,
        conn: Any,
        checkin_id: int,
        results: List[Dict[str, Any]],
    ) -> None:
        rows = []
        for r in results:
            rows.append((
                checkin_id,
                r.get("check_id", ""),
                r.get("check_type", ""),
                r.get("status", "pass"),
                r.get("severity", "info"),
                r.get("executed_at", utc_now_iso()),
                int(r.get("duration_ms", 0)),
                r.get("value"),
                r.get("unit", ""),
                r.get("message", ""),
                json.dumps(r.get("evidence", [])),
                int(r.get("consecutive_failures", 0)),
                int(r.get("is_baseline_anomaly", 0)),
            ))
        if rows:
            conn.executemany(
                """INSERT INTO check_results
                   (check_in_id, check_id, check_type, status, severity,
                    executed_at, duration_ms, value, unit, message,
                    evidence, consecutive_failures, is_baseline_anomaly)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )

    def get_latest_sequence(self, agent_id: str) -> int:
        """Return the highest sequence number for an agent, or 0 if none."""
        row = self.store.connection.query_one(
            "SELECT MAX(sequence) AS seq FROM check_ins WHERE agent_id = ?",
            (agent_id,),
        )
        return int(row["seq"] or 0) if row else 0

    def list_checkins(
        self,
        agent_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        rows = self.store.connection.query(
            """SELECT id, agent_id, sequence, agent_timestamp, received_at,
                      hostname, agent_version, status, observations, breaches,
                      alerts, anomalies, escalations, blocked, errors
               FROM check_ins
               WHERE agent_id = ?
               ORDER BY received_at DESC
               LIMIT ?""",
            (agent_id, safe_limit),
        )
        return [dict(r) for r in rows]

    def get_checkin_results(self, checkin_id: int) -> List[Dict[str, Any]]:
        rows = self.store.connection.query(
            """SELECT check_id, check_type, status, severity,
                      executed_at, duration_ms, value, unit, message,
                      evidence, consecutive_failures, is_baseline_anomaly
               FROM check_results WHERE check_in_id = ?""",
            (checkin_id,),
        )
        results = []
        for r in rows:
            d = dict(r)
            d["evidence"] = json.loads(d["evidence"]) if d["evidence"] else []
            results.append(d)
        return results
