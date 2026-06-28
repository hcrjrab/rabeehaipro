"""Agent registry endpoints.

Read-only views over the orchestrator's agent pool. Useful for the UI to
show which specialists are available and their tool budget.
"""

from __future__ import annotations

from fastapi import APIRouter

from ...config.schemas import AgentRole
from ...orchestration.runner import get_orchestrator

router = APIRouter()


@router.get("")
async def list_agents() -> dict[str, object]:
    """List currently-registered agents (role -> name)."""
    orch = get_orchestrator()
    return {
        "agents": [
            {"role": role.value, "name": agent.name} for role, agent in sorted(orch._agents.items())
        ]
    }


@router.get("/roles")
async def list_roles() -> dict[str, list[str]]:
    """Enumerate the canonical agent roles (independent of registration)."""
    return {"roles": [r.value for r in AgentRole]}
