"""Tribe listing and detail. Tribes emerge in Phase 4."""

from fastapi import APIRouter

from app.api.dto.society import TribeDTO
from app.api.errors import not_implemented_yet

router = APIRouter(prefix="/tribes", tags=["tribes"])


@router.get("", response_model=list[TribeDTO], summary="List tribes")
def list_tribes() -> list[TribeDTO]:
    """Return every tribe with members, storage, camp and territory."""
    raise not_implemented_yet("Tribes", phase=4)


@router.get("/{tribe_id}", response_model=TribeDTO, summary="Tribe detail")
def get_tribe(tribe_id: int) -> TribeDTO:
    """Return one tribe."""
    raise not_implemented_yet("Tribes", phase=4)
