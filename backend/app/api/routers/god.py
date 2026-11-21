"""God tools: the observer's only way to touch the world. Phase 6."""

from fastapi import APIRouter

from app.api.dto.god import GodAction, GodActionRequest, GodActionResultDTO
from app.api.errors import not_implemented_yet

router = APIRouter(prefix="/god", tags=["god"])


@router.post("/{action}", response_model=GodActionResultDTO, summary="Intervene")
def act(action: GodAction, request: GodActionRequest) -> GodActionResultDTO:
    """Drop food, start a drought or a plague, spawn an agent, or smite one."""
    raise not_implemented_yet(f"God tool {action.value!r}", phase=6)
