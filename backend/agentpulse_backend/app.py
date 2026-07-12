"""FastAPI application for AgentPulse backend.

New routes use /v1/ prefix and are mounted here.
The old /api/ routes are preserved for backward compatibility during migration.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .database import ensure_schema, Store
from .settings import load_settings
from .store import Principal as LegacyPrincipal
from .api.routes import agents, audit, checkin, enrollment, incidents

settings = load_settings()


def create_app(db_path: Optional[str] = None) -> FastAPI:
    app_store = Store(db_path or settings.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Run migrations on startup — safe to call repeatedly
        ensure_schema(app_store.db_path)
        yield

    app = FastAPI(
        title="AgentPulse Backend",
        version="1.0.0",
        description="Self-healing server monitoring and remediation API.",
        lifespan=lifespan,
    )

    # ── Global exception handler ────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Don't leak internal errors
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": "An internal error occurred",
                "request_id": request.headers.get("X-Request-ID", ""),
            },
        )

    # ── New v1 routes ──────────────────────────────────────────────────────────
    app.include_router(enrollment.create_enrollment_router(app_store), prefix="/v1")
    app.include_router(agents.create_agents_router(app_store), prefix="/v1")
    app.include_router(checkin.create_checkin_router(app_store), prefix="/v1")
    app.include_router(incidents.create_incidents_router(app_store), prefix="/v1")
    app.include_router(audit.create_audit_router(app_store), prefix="/v1")

    # ── Backward-compatible legacy routes (old agent format) ────────────────────
    # These use the flat payload format the existing agent sends.
    # The old Store methods are still on the legacy store.
    from .store import Store as LegacyStore

    legacy_store = LegacyStore(db_path or settings.db_path)
    # NOTE: legacy_store.init_db() intentionally omitted.
    # ensure_schema(app_store.db_path) already ran in the lifespan startup.

    def require_principal(authorization: str = Header("")) -> LegacyPrincipal:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="missing bearer token")
        principal = legacy_store.authenticate_api_key(token)
        if principal is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="invalid bearer token")
        return principal

    @app.post("/api/agent/checkin")
    async def legacy_checkin(request: Request, principal: LegacyPrincipal = Depends(require_principal)):
        payload = await request.json()
        try:
            recorded = legacy_store.record_checkin(org_id=principal.org_id, payload=payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **recorded}

    @app.get("/api/agents")
    def legacy_list_agents(principal: LegacyPrincipal = Depends(require_principal)):
        return {"ok": True, "agents": legacy_store.list_agents(org_id=principal.org_id)}

    @app.get("/api/agents/{agent_id}/checkins")
    def legacy_list_checkins(agent_id: str, limit: int = 50, principal: LegacyPrincipal = Depends(require_principal)):
        return {
            "ok": True,
            "agent_id": agent_id,
            "checkins": legacy_store.list_checkins(org_id=principal.org_id, agent_id=agent_id, limit=limit),
        }

    # ── Health ──────────────────────────────────────────────────────────────────
    @app.get("/health", tags=["health"])
    def health() -> Dict[str, Any]:
        return {
            "ok": True,
            "service": "agentpulse-backend",
            "version": "1.0.0",
            "database": app_store.db_path,
        }

    @app.get("/ready", tags=["health"])
    def ready():
        # Verify we can reach the database
        try:
            app_store.connection.query_one("SELECT 1")
            return {"status": "ready", "database": "ok"}
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "database": str(exc)},
            )

    return app


app = create_app()
