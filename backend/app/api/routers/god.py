"""God tools: the observer's only way to touch a running world (SPEC 9.4)."""

from fastapi import APIRouter

from app.api.deps import SimulationDep
from app.api.dto.god import GodAction, GodActionRequest, GodActionResultDTO
from app.api.errors import bad_request
from app.services.god_tools import Intervention

router = APIRouter(prefix="/god", tags=["god"])


@router.post("/{action}", response_model=GodActionResultDTO, summary="Intervene")
async def act(
    action: GodAction, request: GodActionRequest, simulation: SimulationDep
) -> GodActionResultDTO:
    """Drop food, start a drought or a plague, spawn an agent, or smite one.

    The response describes what actually happened, not what was asked for:
    the tool runs on the engine thread and this waits for it, so "smite an
    agent that is already dead" comes back as `affected: 0` with a reason.
    """
    try:
        outcome = await simulation.intervene(
            action.value,
            Intervention(
                x=request.x,
                z=request.z,
                radius=request.radius,
                amount=request.amount,
                agent_id=request.agent_id,
                strategy=request.strategy,
                brain_type=request.brain_type,
            ),
        )
    except KeyError as error:
        raise bad_request(str(error)) from error

    return GodActionResultDTO(action=action, affected=outcome.affected, detail=outcome.detail)
