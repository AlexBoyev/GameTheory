"""Simulation state and control (SPEC section 8).

Control endpoints are async because they wait for the engine thread to apply
their command before reporting state - so `POST /sim/step` returns the tick
the step actually produced, not the one before it.
"""

from fastapi import APIRouter

from app.api.deps import SimulationDep
from app.api.dto.sim import (
    PresetDTO,
    ResetRequest,
    SimStateDTO,
    SpeedRequest,
    StepRequest,
)
from app.api.errors import bad_request
from app.core.world_config import WorldConfig
from app.services.simulation_service import SimStateView

router = APIRouter(prefix="/sim", tags=["sim"])

PRESETS: tuple[PresetDTO, ...] = (
    PresetDTO(
        id="peaceful_eden",
        name="Peaceful Eden",
        description="Abundant food, cooperative strategy mix - watch trust accumulate.",
    ),
    PresetDTO(
        id="harsh_winter",
        name="Harsh Winter",
        description="Scarcity high, no berry regrowth - cooperation under pressure.",
    ),
    PresetDTO(
        id="liars_island",
        name="Liars' Island",
        description="Low honesty, high cunning - gossip and deception dominate.",
    ),
    PresetDTO(
        id="tribal_wars",
        name="Tribal Wars",
        description="Several starting tribes, contested territory, raids and peace deals.",
    ),
    PresetDTO(
        id="axelrod_tournament",
        name="Axelrod Tournament",
        description="Survival off: round-robin iterated PD with replicator dynamics.",
    ),
    PresetDTO(
        id="llm_schemers",
        name="LLM Schemers",
        description="A handful of LLM minds among utility agents - they plot out loud.",
    ),
)
"""Preset catalogue. Phase 6 loads the actual values from `config/presets/`."""


def _to_dto(state: SimStateView) -> SimStateDTO:
    return SimStateDTO(
        status=state.status.value,
        tick=state.tick,
        speed=state.speed,
        seed=state.seed,
        day=state.day,
        season=state.season,
        time_of_day=state.time_of_day,
        is_night=state.is_night,
        population=state.population,
        ticks_per_second=state.ticks_per_second,
        placeholder=state.placeholder,
    )


@router.get("/state", response_model=SimStateDTO, summary="Current simulation state")
def get_state(simulation: SimulationDep) -> SimStateDTO:
    """Return status, tick, speed, seed, day, season and population."""
    return _to_dto(simulation.state())


@router.post("/start", response_model=SimStateDTO, summary="Resume ticking")
async def start(simulation: SimulationDep) -> SimStateDTO:
    """Resume the simulation."""
    return _to_dto(await simulation.play())


@router.post("/pause", response_model=SimStateDTO, summary="Pause ticking")
async def pause(simulation: SimulationDep) -> SimStateDTO:
    """Pause the simulation, keeping the world."""
    return _to_dto(await simulation.pause())


@router.post("/step", response_model=SimStateDTO, summary="Advance n ticks")
async def step(request: StepRequest, simulation: SimulationDep) -> SimStateDTO:
    """Advance exactly `n` ticks and stay paused."""
    try:
        return _to_dto(await simulation.step(request.n))
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


@router.post("/speed", response_model=SimStateDTO, summary="Set the speed multiplier")
async def set_speed(request: SpeedRequest, simulation: SimulationDep) -> SimStateDTO:
    """Set speed to one of the presets; `0` pauses and `-1` means MAX."""
    try:
        return _to_dto(await simulation.set_speed(request.multiplier))
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


@router.post("/reset", response_model=SimStateDTO, summary="Build a new world")
async def reset(request: ResetRequest, simulation: SimulationDep) -> SimStateDTO:
    """Rebuild the world; it stays paused at tick 0 so you can inspect it first.

    `preset` is accepted but only applied from Phase 6, when the preset files
    carry values.
    """
    return _to_dto(await simulation.reset(seed=request.seed, config=request.config))


@router.get("/config", response_model=WorldConfig, summary="Current world config")
def get_config(simulation: SimulationDep) -> WorldConfig:
    """Return the config the current world was built from."""
    return simulation.config


@router.put("/config", response_model=SimStateDTO, summary="Replace the world config")
async def put_config(config: WorldConfig, simulation: SimulationDep) -> SimStateDTO:
    """Apply a new config.

    A running world cannot change its own population or terrain, so this
    rebuilds it - equivalent to `POST /sim/reset` with a config.
    """
    return _to_dto(await simulation.reset(config=config))


@router.get("/presets", response_model=list[PresetDTO], summary="Named world presets")
def presets() -> list[PresetDTO]:
    """Return the preset catalogue."""
    return list(PRESETS)
