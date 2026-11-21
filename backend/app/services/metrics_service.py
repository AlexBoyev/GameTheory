"""Computes and serves the time series behind the charts panel (SPEC 10).

Sampling every N ticks (not every tick) is deliberate: at MAX speed the charts
must not become the bottleneck.
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.settings import Settings
from app.persistence.repository import Repository


@dataclass(frozen=True, slots=True)
class MetricPoint:
    """One sample of the global metrics."""

    tick: int
    sim_seconds: float
    population: int
    births: int = 0
    deaths: int = 0
    cooperation_rate: float = 0.0
    food_gini: float = 0.0
    trust_density: float = 0.0
    by_tribe: dict[str, int] = field(default_factory=dict)
    by_strategy: dict[str, int] = field(default_factory=dict)
    payoff_by_strategy: dict[str, float] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


class MetricsService:
    """Samples the world on a tick interval and exposes the series."""

    __slots__ = ("_repository", "_series", "sample_every_ticks")

    def __init__(
        self,
        settings: Settings,
        repository: Repository | None = None,
        sample_every_ticks: int = 100,
    ) -> None:
        self._repository = repository
        self.sample_every_ticks = sample_every_ticks
        self._series: list[MetricPoint] = []
        _ = settings

    @property
    def latest(self) -> MetricPoint | None:
        """Most recent sample, if any."""
        return self._series[-1] if self._series else None

    def series(self, from_tick: int = 0) -> list[MetricPoint]:
        """Return samples at or after `from_tick`."""
        return [point for point in self._series if point.tick >= from_tick]

    def should_sample(self, tick: int) -> bool:
        """Whether `tick` is a sampling tick."""
        return tick > 0 and tick % self.sample_every_ticks == 0

    def record(self, point: MetricPoint) -> None:
        """Append a sample (and persist it once Phase 4 wires the repository)."""
        self._series.append(point)

    def compute(self, tick: int) -> MetricPoint:
        """Compute a sample from the current world. Implemented in Phase 4."""
        msg = "MetricsService.compute() arrives in Phase 4 (metrics)"
        raise NotImplementedError(msg)
