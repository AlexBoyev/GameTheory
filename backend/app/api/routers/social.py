"""The social graph: who trusts whom (SPEC section 6)."""

from fastapi import APIRouter, Query

from app.api.deps import SimulationDep
from app.api.dto.society import TrustEdgeDTO, TrustGraphDTO

router = APIRouter(prefix="/social", tags=["social"])


@router.get("/trust-graph", response_model=TrustGraphDTO, summary="Strongest bonds and feuds")
def trust_graph(
    simulation: SimulationDep,
    minimum: float = Query(default=0.25, ge=0.0, le=1.0, description="Minimum |trust| to include."),
    limit: int = Query(default=400, ge=1, le=5000),
) -> TrustGraphDTO:
    """Return the strongest relationships, strongest first.

    Thresholded on purpose: every agent knows dozens of others, so an
    unfiltered graph is tens of thousands of edges and draws as grey fog.
    """
    payload = simulation.queries.trust_graph(minimum=minimum, limit=limit)
    return TrustGraphDTO(
        edges=[TrustEdgeDTO(**edge) for edge in payload["edges"]],
        total=payload["total"],
    )
