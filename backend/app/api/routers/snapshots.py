"""Save and load worlds (SPEC section 11)."""

from fastapi import APIRouter

from app.api.deps import SimulationDep, SnapshotsDep
from app.api.dto.common import AckDTO
from app.api.dto.observability import SnapshotCreateRequest, SnapshotDTO
from app.api.errors import not_found
from app.services.snapshot_service import SnapshotMeta

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


def _to_dto(meta: SnapshotMeta) -> SnapshotDTO:
    """Shape one listing row."""
    return SnapshotDTO(
        id=meta.id,
        label=meta.label,
        tick=meta.tick,
        seed=meta.seed,
        population=meta.population,
        created_at=meta.created_at,
        size_bytes=meta.size_bytes,
    )


@router.get("", response_model=list[SnapshotDTO], summary="List saved snapshots")
def list_snapshots(snapshots: SnapshotsDep, limit: int = 50) -> list[SnapshotDTO]:
    """Return snapshot metadata, newest first."""
    return [_to_dto(meta) for meta in snapshots.list_snapshots(limit)]


@router.post("", response_model=SnapshotDTO, summary="Save the current world")
def create_snapshot(
    request: SnapshotCreateRequest, snapshots: SnapshotsDep, simulation: SimulationDep
) -> SnapshotDTO:
    """Serialise and store the current world.

    Terrain is not stored - it comes back from the config and the seed - but
    agents, resources, tribes, shelters and every agent's memories are.
    """
    return _to_dto(snapshots.save(request.label, simulation.capture()))


@router.post("/{snapshot_id}/load", response_model=AckDTO, summary="Load a snapshot")
async def load_snapshot(
    snapshot_id: int, snapshots: SnapshotsDep, simulation: SimulationDep
) -> AckDTO:
    """Replace the running world with a saved one, paused at its saved tick."""
    payload = snapshots.read(snapshot_id)
    if payload is None:
        raise not_found(f"No snapshot with id {snapshot_id}")

    state = await simulation.restore(payload)
    return AckDTO(ok=True, detail=f"loaded tick {state.tick} with {state.population} agents")
