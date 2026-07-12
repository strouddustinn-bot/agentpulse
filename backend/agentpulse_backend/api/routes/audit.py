"""Audit routes — GET /v1/audit-events."""

from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Optional

from ...repositories.audit import AuditRepository
from ...schemas import AuditEventListResponse, AuditEventResponse

router = APIRouter(prefix="/audit-events", tags=["audit"])


def create_audit_router(store) -> APIRouter:
    repo = AuditRepository(store)

    @router.get(
        "",
        response_model=AuditEventListResponse,
        summary="List audit events",
    )
    def list_audit_events(
        agent_id: Optional[str] = Query(None),
        incident_id: Optional[str] = Query(None),
        event_type: Optional[str] = Query(None),
        limit: int = Query(100, ge=1, le=500),
    ) -> AuditEventListResponse:
        events = repo.list(
            agent_id=agent_id,
            incident_id=incident_id,
            event_type=event_type,
            limit=limit,
        )
        return AuditEventListResponse(
            events=[AuditEventResponse(**e) for e in events],
        )

    return router
