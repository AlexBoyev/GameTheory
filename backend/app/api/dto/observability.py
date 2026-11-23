"""Metrics, events and snapshot DTOs (SPEC sections 10, 11)."""

from pydantic import BaseModel, ConfigDict, Field


class MetricPointDTO(BaseModel):
    """One sample in the metrics series."""

    model_config = ConfigDict(extra="forbid")

    tick: int
    sim_seconds: float
    population: int
    births: int = 0
    deaths: int = 0
    cooperation_rate: float = 0.0
    food_gini: float = 0.0
    trust_density: float = 0.0
    deaths_by_cause: dict[str, int] = Field(default_factory=dict)
    by_tribe: dict[str, int] = Field(default_factory=dict)
    by_strategy: dict[str, int] = Field(default_factory=dict)
    payoff_by_strategy: dict[str, float] = Field(default_factory=dict)
    cooperation_by_game: dict[str, float] = Field(default_factory=dict)
    extra: dict[str, float] = Field(
        default_factory=dict,
        description="Counters: tribes, shelters, betrayals, lies, wars and so on.",
    )


class MetricsDTO(BaseModel):
    """`GET /api/metrics?from_tick=`."""

    model_config = ConfigDict(extra="forbid")

    from_tick: int = 0
    sample_every_ticks: int = 100
    points: list[MetricPointDTO] = Field(default_factory=list)


class EventDTO(BaseModel):
    """One row of the event feed; `x`/`z` let the camera fly there."""

    model_config = ConfigDict(extra="forbid")

    tick: int
    type: str
    summary: str
    importance: int = 3
    actors: list[int] = Field(default_factory=list)
    x: float | None = None
    z: float | None = None


class EventsDTO(BaseModel):
    """`GET /api/events?limit=&type=`."""

    model_config = ConfigDict(extra="forbid")

    items: list[EventDTO] = Field(default_factory=list)


class SnapshotDTO(BaseModel):
    """Snapshot listing row."""

    model_config = ConfigDict(extra="forbid")

    id: int
    label: str
    tick: int
    seed: int
    population: int
    created_at: str
    size_bytes: int


class SnapshotCreateRequest(BaseModel):
    """`POST /api/snapshots`."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="", max_length=120)
