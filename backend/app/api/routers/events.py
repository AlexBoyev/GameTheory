"""The event feed (SPEC sections 8, 10)."""

from fastapi import APIRouter, Query

from app.api.deps import SimulationDep
from app.api.dto.observability import EventDTO, EventsDTO

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventsDTO, summary="Recent events")
def list_events(
    simulation: SimulationDep,
    limit: int = Query(default=100, ge=1, le=1000),
    type: str | None = Query(default=None, description="Filter by event type."),
) -> EventsDTO:
    """Return the newest events, newest first, optionally filtered by type.

    Backed by an in-memory ring buffer: the SQLite event log arrives with the
    metrics in Phase 4.
    """
    items = simulation.recent_events(limit=limit, event_type=type)
    return EventsDTO(items=[EventDTO(**item) for item in items])
