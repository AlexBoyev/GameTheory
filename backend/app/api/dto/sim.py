"""Simulation state and control DTOs (SPEC section 8)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.world_config import WorldConfig


class SimStateDTO(BaseModel):
    """`GET /api/sim/state`."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="stopped | running | paused")
    tick: int
    speed: float = Field(description="Multiplier; -1 means MAX.")
    seed: int
    day: int
    season: str
    time_of_day: float = Field(ge=0.0, lt=1.0)
    is_night: bool
    population: int
    ticks_per_second: float
    skip_remaining: int = Field(
        default=0,
        description="Ticks still owed to a step. Non-zero means a skip is running.",
    )
    placeholder: bool = Field(
        default=False,
        description="True while the Phase 1 placeholder world is driving frames.",
    )


class SpeedRequest(BaseModel):
    """`POST /api/sim/speed`."""

    model_config = ConfigDict(extra="forbid")

    multiplier: float = Field(description="One of 0, 1, 2, 5, 10, 25, 50, -1 (MAX).")


class StepRequest(BaseModel):
    """`POST /api/sim/step`."""

    model_config = ConfigDict(extra="forbid")

    n: int = Field(
        default=1,
        ge=1,
        le=24_000,
        description="Ticks to advance. A day is 2,400; the cap is ten days.",
    )


class ResetRequest(BaseModel):
    """`POST /api/sim/reset`. Leaves the world paused at tick 0."""

    model_config = ConfigDict(extra="forbid")

    seed: int | None = None
    preset: str | None = None
    config: WorldConfig | None = None
    overrides: dict[str, Any] | None = Field(
        default=None,
        description="Fields applied last, after any preset. What the dials send.",
    )
    """The user's own choices, kept apart from the base they sit on.

    A preset is overrides on top of `config`, so anything the preset names
    wins - which made the documented "Tribal Wars, but 400 agents" request
    impossible: the preset's own population overwrote the one you asked for,
    silently. The server cannot tell a field you *chose* from a field that
    merely carries a default, so the client says so here instead.
    """


class PresetDTO(BaseModel):
    """One named world preset (`GET /api/sim/presets`)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""


class TournamentStandingDTO(BaseModel):
    """One strategy's result in the current generation."""

    model_config = ConfigDict(extra="forbid")

    strategy: str
    score_per_round: float
    members: int


class TournamentDTO(BaseModel):
    """`GET /api/sim/tournament` - the Axelrod report (SPEC 5.3)."""

    model_config = ConfigDict(extra="forbid")

    active: bool = Field(description="False unless the world is in tournament mode.")
    generation: int = 0
    generations: int = 0
    finished: bool = False
    pairings_played: int = 0
    pairings_total: int = 0
    standings: list[TournamentStandingDTO] = Field(default_factory=list)
