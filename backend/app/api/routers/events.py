"""The event feed (SPEC sections 8, 10).

Served from the in-memory ring first and topped up from the run archive,
so a request that reaches past the ring still gets history instead of a
short list.
"""

from fastapi import APIRouter, Query

from app.api.deps import ArchiveDep, SimulationDep
from app.api.dto.observability import EventDTO, EventsDTO

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventsDTO, summary="Recent events")
def list_events(
    simulation: SimulationDep,
    archive: ArchiveDep,
    limit: int = Query(default=100, ge=1, le=1000),
    type: str | None = Query(default=None, description="Filter by event type."),
) -> EventsDTO:
    """Return the newest events, newest first, optionally filtered by type.

    The ring buffer holds the recent past per type; anything older comes from
    SQLite. Rows already in memory are not fetched twice - the archive is
    only asked for the shortfall, and only for ticks the ring no longer
    reaches.
    """
    items = simulation.recent_events(limit=limit, event_type=type)
    if len(items) < limit:
        oldest = items[-1]["tick"] if items else None
        seen = {(item["tick"], item["type"], item["summary"]) for item in items}
        for row in archive.past_events(limit=limit, event_type=type):
            if len(items) >= limit:
                break
            if oldest is not None and row["tick"] > oldest:
                continue
            if (row["tick"], row["type"], row["summary"]) in seen:
                continue
            items.append(row)
    return EventsDTO(items=[EventDTO(**item) for item in items])
