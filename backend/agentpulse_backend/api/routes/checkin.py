"""Check-in route — POST /v1/agents/check-in."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status
from typing import Annotated, Optional

from ...repositories.agent import AgentRepository
from ...repositories.checkin import CheckinRepository
from ...repositories.incident import IncidentRepository
from ...repositories.audit import AuditRepository
from ...schemas import (
    CheckinRequest,
    CheckinResponse,
    CheckResultSchema,
    ErrorResponse,
    RemediationRequestSchema,
)

router = APIRouter(prefix="/agents", tags=["checkins"])


def create_checkin_router(store) -> APIRouter:
    agent_repo = AgentRepository(store)
    checkin_repo = CheckinRepository(store)
    incident_repo = IncidentRepository(store)
    audit_repo = AuditRepository(store)

    def _require_agent(authorization: str = Header("")) -> dict:
        """Validate Bearer credential and return agent dict."""
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer credential")
        credential = authorization[7:].strip()
        if not credential:
            raise HTTPException(status_code=401, detail="Empty bearer credential")
        agent = agent_repo.authenticate_agent(credential)
        if agent is None:
            raise HTTPException(status_code=401, detail="Invalid or expired agent credential")
        return agent

    @router.post(
        "/check-in",
        response_model=CheckinResponse,
        summary="Receive a check-in from an agent",
        responses={
            401: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    async def checkin(
        request: CheckinRequest,
        x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
        authorization: str = Header(""),
    ) -> CheckinResponse:
        auth = _require_agent(authorization)
        agent_id = auth["agent_id"]
        tenant_id = auth["tenant_id"]

        # Use request idempotency key, or fall back to agent-provided
        idempotency_key = (
            x_idempotency_key
            or f"{agent_id}:{request.sequence}:{request.timestamp}"
        )

        # Record check-in (idempotent — duplicate key returns existing ID)
        checkin_id, is_duplicate = checkin_repo.record_checkin(
            agent_id=agent_id,
            idempotency_key=idempotency_key,
            sequence=request.sequence,
            agent_timestamp=request.timestamp,
            hostname=request.hostname,
            agent_version=request.agent_version,
            config_version=request.config_version,
            status=request.results[0].status.value if request.results else "pass",
            uptime_seconds=request.uptime_seconds,
            observations=len(request.results),
            breaches=sum(1 for r in request.results if r.status.value in ("fail", "warn")),
            alerts=0,
            anomalies=sum(1 for r in request.results if r.is_baseline_anomaly),
            escalations=0,
            blocked=0,
            errors=sum(1 for r in request.results if r.status.value == "error"),
            offline_queue_depth=request.offline_queue_depth,
            check_results=[r.model_dump() for r in request.results],
        )

        # Update agent last-seen
        agent_repo.update_last_seen(agent_id, tenant_id)

        # Process check results → incident lifecycle
        opened_incidents = []
        resolved_incidents = []
        for result in request.results:
            if result.status.value == "pass":
                # Check recovered — resolve any open incidents for this check
                resolved = incident_repo.resolve_incidents_for_check(
                    agent_id=agent_id,
                    check_id=result.check_id,
                    resolved_by="agent",
                    note=f"Check recovered: {result.check_id}",
                    tenant_id=tenant_id,
                )
                resolved_incidents.extend(resolved)
            else:
                # Check failed — open or update an incident
                incident, _ = incident_repo.upsert_incident_from_check_result(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    check_id=result.check_id,
                    check_type=result.check_type,
                    severity=result.severity.value,
                    title=f"[{result.severity.value.upper()}] {result.check_type}: {result.message or result.status.value}",
                    evidence=result.evidence or [],
                )
                if incident:
                    opened_incidents.append(incident)

        # Record audit event
        try:
            audit_repo.record(
                component="backend",
                event_type="checkin_received",
                actor="agent",
                agent_id=agent_id,
                outcome="success" if not opened_incidents else "incidents_opened",
                body={
                    "checkin_id": checkin_id,
                    "is_duplicate": is_duplicate,
                    "sequence": request.sequence,
                    "incidents_opened": len(opened_incidents),
                    "incidents_resolved": len(resolved_incidents),
                },
                tenant_id=tenant_id,
            )
        except Exception:
            pass  # audit failure is non-fatal

        # Return server time for clock sync
        from ...database.connection import utc_now_iso
        return CheckinResponse(
            acknowledged=True,
            actions=[],  # pending actions would be dispatched here
            policy_version="",
            server_time=utc_now_iso(),
        )

    return router
