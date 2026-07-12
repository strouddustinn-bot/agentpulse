"""Incident routes — GET /v1/incidents, GET /v1/incidents/{id}."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional

from ...repositories.incident import IncidentRepository
from ...schemas import (
    AcknowledgeRequest,
    IncidentEventResponse,
    IncidentListResponse,
    IncidentResponse,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])


def create_incidents_router(store) -> APIRouter:
    repo = IncidentRepository(store)

    @router.get(
        "",
        response_model=IncidentListResponse,
        summary="List incidents",
    )
    def list_incidents(
        status_filter: Optional[str] = Query(None, alias="status"),
        agent_id: Optional[str] = Query(None),
        severity: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
    ) -> IncidentListResponse:
        incidents = repo.list_incidents(
            status=status_filter,
            agent_id=agent_id,
            severity=severity,
            limit=limit,
        )
        return IncidentListResponse(
            incidents=[IncidentResponse(**i) for i in incidents],
            total=len(incidents),
        )

    @router.get(
        "/{incident_id}",
        response_model=IncidentResponse,
        summary="Get incident details",
    )
    def get_incident(incident_id: str) -> IncidentResponse:
        incident = repo.get_incident(incident_id)
        if incident is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        return IncidentResponse(**incident)

    @router.post(
        "/{incident_id}/acknowledge",
        response_model=IncidentResponse,
        summary="Acknowledge an incident",
    )
    def acknowledge_incident(
        incident_id: str,
        body: AcknowledgeRequest,
    ) -> IncidentResponse:
        incident = repo.acknowledge_incident(incident_id, note=body.note)
        if incident is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        return IncidentResponse(**incident)

    @router.post(
        "/{incident_id}/resolve",
        response_model=IncidentResponse,
        summary="Resolve an incident",
    )
    def resolve_incident(incident_id: str) -> IncidentResponse:
        incident = repo.resolve_incident(incident_id)
        if incident is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        return IncidentResponse(**incident)

    @router.get(
        "/{incident_id}/events",
        summary="Get incident event timeline",
    )
    def get_incident_events(incident_id: str) -> dict:
        events = repo.get_incident_events(incident_id)
        return {"events": [IncidentEventResponse(**e) for e in events]}

    return router
