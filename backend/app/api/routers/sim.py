"""Simulation state and control (SPEC section 8).

Control endpoints are async because they wait for the engine thread to apply
their command before reporting state - so `POST /sim/step` returns the tick
the step actually produced, not the one before it.
"""

from pathlib import Path

from fastapi import APIRouter
from pydantic import ValidationError

from app.api.deps import SettingsDep, SimulationDep
from app.api.dto.sim import (
    PresetDTO,
    ResetRequest,
    SimStateDTO,
    SpeedRequest,
    StepRequest,
    TournamentDTO,
    TournamentStandingDTO,
)
from app.api.errors import bad_request, not_found, unprocessable
from app.core.presets import load_preset, load_presets
from app.core.world_config import WorldConfig
from app.services.engine_factory import world_config_from_settings
from app.services.simulation_service import SimStateView

router = APIRouter(prefix="/sim", tags=["sim"])


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
async def reset(
    request: ResetRequest, simulation: SimulationDep, settings: SettingsDep
) -> SimStateDTO:
    """Rebuild the world; it stays paused at tick 0 so you can inspect it first.

    Three layers, applied in that order: `config` (or the defaults), then a
    `preset` named from `config/presets/`, then `overrides`. That last layer
    is what makes "Tribal Wars, but 400 agents" a single request - the
    docstring claimed it before the layer existed, and the preset's own
    population quietly won instead.

    The seed is never overridden by a preset: picking one must not throw
    away a seed typed in beside it.
    """
    config = request.config
    if request.preset is not None:
        preset = load_preset(request.preset, Path(settings.config_dir))
        if preset is None:
            raise not_found(f"No preset named {request.preset!r}")
        config = preset.apply_to(config or WorldConfig())
    if request.overrides:
        merged = (config or WorldConfig()).model_copy(update=request.overrides)
        # Round-trip so an override is validated like any other config field
        # rather than trusted into the world: `model_copy` does not validate,
        # so a negative population would otherwise reach world generation.
        try:
            config = WorldConfig.model_validate(merged.model_dump(mode="json"))
        except ValidationError as error:
            raise unprocessable(f"invalid override: {error.errors()[0]['msg']}") from error

    return _to_dto(await simulation.reset(seed=request.seed, config=config))


@router.get("/defaults", response_model=WorldConfig, summary="Default world config")
def defaults(settings: SettingsDep) -> WorldConfig:
    """The config a world is built from when nothing overrides it.

    The New World dialog needs this to mean "a default island": a bare reset
    rebuilds from the *current* config, so without it, choosing the Axelrod
    preset once left `tournament_mode` on with no way back - an island with
    no decision system, which looks exactly like a broken simulation.
    """
    return world_config_from_settings(settings)


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
def presets(settings: SettingsDep) -> list[PresetDTO]:
    """Return the preset catalogue, read from `config/presets/`."""
    return [
        PresetDTO(id=preset.id, name=preset.name, description=preset.description)
        for preset in load_presets(Path(settings.config_dir))
    ]


@router.get("/tournament", response_model=TournamentDTO, summary="Axelrod standings")
def tournament(simulation: SimulationDep) -> TournamentDTO:
    """Report the tournament (SPEC 5.3), or `active: false` on a normal island.

    Answers on any world rather than 404ing off-tournament, so the UI can ask
    once and decide whether to show the panel at all.
    """
    report = simulation.tournament()
    return TournamentDTO(
        active=report.active,
        generation=report.generation,
        generations=report.generations,
        finished=report.finished,
        pairings_played=report.pairings_played,
        pairings_total=report.pairings_total,
        standings=[
            TournamentStandingDTO(strategy=name, score_per_round=score, members=members)
            for name, score, members in report.standings
        ],
    )
