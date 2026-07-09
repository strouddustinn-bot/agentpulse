"""FastAPI app for AgentPulse backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from . import __version__
from .settings import load_settings
from .store import Principal, Store, StoreError

settings = load_settings()


def create_app(db_path: Optional[str] = None) -> FastAPI:
    app_store = Store(db_path or settings.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_store.init_db()
        yield

    app = FastAPI(
        title="AgentPulse Backend",
        version=__version__,
        description="Agent check-in, fleet status, and license API for AgentPulse.",
        lifespan=lifespan,
    )

    def require_principal(authorization: str = Header(default="")) -> Principal:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="missing bearer token")
        principal = app_store.authenticate_api_key(token)
        if principal is None:
            raise HTTPException(status_code=401, detail="invalid bearer token")
        return principal

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {"ok": True, "service": "agentpulse-backend", "version": __version__}

    @app.post("/api/agent/checkin")
    async def checkin(
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> Dict[str, Any]:
        try:
            payload = await request.json()
            recorded = app_store.record_checkin(
                org_id=principal.org_id, payload=payload
            )
        except StoreError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **recorded}

    @app.get("/api/agents")
    def list_agents(
        principal: Principal = Depends(require_principal),
    ) -> Dict[str, Any]:
        return {"ok": True, "agents": app_store.list_agents(org_id=principal.org_id)}

    @app.get("/api/agents/{agent_id}/checkins")
    def list_agent_checkins(
        agent_id: str,
        limit: int = 50,
        principal: Principal = Depends(require_principal),
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "agent_id": agent_id,
            "checkins": app_store.list_checkins(
                org_id=principal.org_id,
                agent_id=agent_id,
                limit=limit,
            ),
        }

    @app.post("/api/license/verify")
    async def verify_license(request: Request) -> Dict[str, Any]:
        payload = await request.json()
        license_key = str(payload.get("license_key", ""))
        agent_id = str(payload.get("agent_id", ""))
        result = app_store.verify_license(license_key=license_key, agent_id=agent_id)
        return {
            "ok": result.active,
            "active": result.active,
            "reason": result.reason,
            "org_id": result.org_id,
            "plan": result.plan,
            "max_agents": result.max_agents,
        }

    return app


app = create_app()
