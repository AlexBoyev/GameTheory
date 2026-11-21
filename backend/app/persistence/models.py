"""Database tables. Snapshots and configs are stored as gzipped JSON blobs."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    """Return the current UTC time (storage layer, so wall clock is fine here)."""
    return datetime.now(UTC)


class Run(SQLModel, table=True):
    """One simulation run: a seed, a config and when it started."""

    __tablename__ = "runs"

    id: int | None = Field(default=None, primary_key=True)
    seed: int
    label: str = ""
    preset: str | None = None
    config_json: str = "{}"
    started_at: datetime = Field(default_factory=_now, index=True)
    ended_at: datetime | None = None
    last_tick: int = 0


class MetricSample(SQLModel, table=True):
    """One metrics row, written every N ticks (SPEC section 10)."""

    __tablename__ = "metric_samples"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    tick: int = Field(index=True)
    sim_seconds: float = 0.0
    population: int = 0
    births: int = 0
    deaths: int = 0
    cooperation_rate: float = 0.0
    food_gini: float = 0.0
    trust_density: float = 0.0
    payload_json: str = "{}"


class SnapshotRecord(SQLModel, table=True):
    """A full world state, gzipped JSON, loadable from the UI."""

    __tablename__ = "snapshots"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int | None = Field(default=None, foreign_key="runs.id", index=True)
    label: str = ""
    tick: int = 0
    seed: int = 0
    population: int = 0
    created_at: datetime = Field(default_factory=_now, index=True)
    size_bytes: int = 0
    blob_gzip: bytes = b""


class EventRecord(SQLModel, table=True):
    """Capped event log backing `GET /api/events`."""

    __tablename__ = "events"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    tick: int = Field(index=True)
    type: str = Field(index=True)
    summary: str = ""
    importance: int = 3
    actors_json: str = "[]"
    x: float | None = None
    z: float | None = None
