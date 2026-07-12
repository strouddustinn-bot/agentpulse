"""Agents routes — GET /v1/agents, GET /v1/agents/{id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated

from ...repositories.agent import AgentRepository
from ...schemas import AgentResponse, AgentListResponse

router = APIRouter(prefix="/agents", tags=["agents"])


def create_agents_router(store) -> APIRouter:
    repo = AgentRepository(store)

    @router.get("", response_model=AgentListResponse, summary="List all agents")
    def list_agents() -> AgentListResponse:
        agents = repo.list_agents()
        return AgentListResponse(
            agents=[AgentResponse(**a) for a in agents],
            total=len(agents),
        )

    @router.get("/{agent_id}", response_model=AgentResponse, summary="Get agent details")
    def get_agent(agent_id: str) -> AgentResponse:
        agent = repo.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return AgentResponse(**agent)

    return router
