"""Save and load worlds (SPEC section 11). Writing arrives in Phase 6."""

from fastapi import APIRouter

from app.api.deps import SnapshotsDep
from app.api.dto.common import AckDTO
from app.api.dto.observability import SnapshotCreateRequest, SnapshotDTO
from app.api.errors import not_implemented_yet

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("", response_model=list[SnapshotDTO], summary="List saved snapshots")
def list_snapshots(snapshots: SnapshotsDep, limit: int = 50) -> list[SnapshotDTO]:
    """Return snapshot metadata, newest first."""
    return [
        SnapshotDTO(
            id=meta.id,
            label=meta.label,
            tick=meta.tick,
            seed=meta.seed,
            population=meta.population,
            created_at=meta.created_at,
            size_bytes=meta.size_bytes,
        )
        for meta in snapshots.list_snapshots(limit)
    ]


@router.post("", response_model=SnapshotDTO, summary="Save the current world")
def create_snapshot(request: SnapshotCreateRequest, snapshots: SnapshotsDep) -> SnapshotDTO:
    """Serialise and store the current world."""
    raise not_implemented_yet("Saving snapshots", phase=6)


@router.post("/{snapshot_id}/load", response_model=AckDTO, summary="Load a snapshot")
def load_snapshot(snapshot_id: int, snapshots: SnapshotsDep) -> AckDTO:
    """Replace the running world with a saved one."""
    raise not_implemented_yet("Loading snapshots", phase=6)
