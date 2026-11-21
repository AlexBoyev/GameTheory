"""Tribe listing and detail (SPEC section 6)."""

from fastapi import APIRouter

from app.api.deps import SimulationDep
from app.api.dto.society import TribeDTO
from app.api.errors import not_found

router = APIRouter(prefix="/tribes", tags=["tribes"])


@router.get("", response_model=list[TribeDTO], summary="List tribes")
def list_tribes(simulation: SimulationDep) -> list[TribeDTO]:
    """Return every tribe with members, storage, camp and territory."""
    return [TribeDTO(**row) for row in simulation.queries.tribes()]


@router.get("/{tribe_id}", response_model=TribeDTO, summary="Tribe detail")
def get_tribe(tribe_id: int, simulation: SimulationDep) -> TribeDTO:
    """Return one tribe."""
    for row in simulation.queries.tribes():
        if row["id"] == tribe_id:
            return TribeDTO(**row)
    raise not_found(f"tribe {tribe_id}")
