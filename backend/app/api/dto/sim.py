"""Simulation state and control DTOs (SPEC section 8)."""

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

    n: int = Field(default=1, ge=1, le=10_000)


class ResetRequest(BaseModel):
    """`POST /api/sim/reset`. Leaves the world paused at tick 0."""

    model_config = ConfigDict(extra="forbid")

    seed: int | None = None
    preset: str | None = None
    config: WorldConfig | None = None


class PresetDTO(BaseModel):
    """One named world preset (`GET /api/sim/presets`)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
