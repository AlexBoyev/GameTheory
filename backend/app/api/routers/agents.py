"""Agent listing and the inspector's detail payload."""

from fastapi import APIRouter, Query

from app.api.deps import SimulationDep
from app.api.dto.society import AgentDetailDTO, AgentSummaryDTO
from app.api.errors import not_found

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentSummaryDTO], summary="List agents")
def list_agents(
    simulation: SimulationDep,
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[AgentSummaryDTO]:
    """Return a summary row per living agent, in id order."""
    return [AgentSummaryDTO(**row) for row in simulation.queries.agent_summaries(limit)]


@router.get("/{agent_id}", response_model=AgentDetailDTO, summary="Full agent detail")
def get_agent(agent_id: int, simulation: SimulationDep) -> AgentDetailDTO:
    """Return needs, traits, memory, relationships and the decision trace."""
    payload = simulation.queries.agent_detail(agent_id)
    if payload is None:
        raise not_found(f"agent {agent_id}")
    return AgentDetailDTO(**payload)
