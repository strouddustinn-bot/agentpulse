"""Enrollment routes — POST /v1/agents/enroll."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ...repositories.agent import AgentRepository
from ...schemas import EnrollmentRequest, EnrollmentResponse

router = APIRouter(prefix="/agents", tags=["enrollment"])


def create_enrollment_router(store) -> APIRouter:
    @router.post(
        "/enroll",
        response_model=EnrollmentResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Enroll a new agent",
    )
    async def enroll(request: EnrollmentRequest) -> EnrollmentResponse:
        """Enroll a new agent using a valid enrollment token.

        Issues a long-lived agent credential (returned only here — store it securely).
        Creates an audit event for the enrollment.
        """
        agents = AgentRepository(store)

        # 1. Validate enrollment token
        consumed = agents.consume_enrollment_token(request.enrollment_token)
        if consumed is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "AGENT_101",
                    "message": "Invalid, expired, or already-used enrollment token",
                },
            )

        tenant_id = consumed["tenant_id"]

        # 2. Create agent + credential
        try:
            agent_id, credential = agents.create_agent(
                hostname=request.hostname,
                os=request.os,
                architecture=request.architecture,
                agent_version=request.agent_version,
                config_version=request.config_version,
                machine_id=request.machine_id,
                checks_offered=request.checks_offered,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error_code": "AGENT_102",
                    "message": f"Failed to create agent record: {exc}",
                },
            )

        # 3. Record audit event
        try:
            from ...repositories.audit import AuditRepository
            audit = AuditRepository(store)
            audit.record(
                component="backend",
                event_type="agent_enrolled",
                actor="enrollment_token",
                agent_id=agent_id,
                outcome="success",
                body={
                    "hostname": request.hostname,
                    "os": request.os,
                    "agent_version": request.agent_version,
                },
                tenant_id=tenant_id,
            )
        except Exception:
            pass  # audit failure is non-fatal to enrollment

        return EnrollmentResponse(
            agent_id=agent_id,
            auth_token=credential,
            backend_url="http://localhost:8088",
            checkin_interval=60,
            policy={},
        )

    return router
