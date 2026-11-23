"""One sample of the global metrics (SPEC section 10).

Its own module because two collaborators need it and neither should own it:
`MetricsService` computes points from the live world, and `RunArchive` writes
them to SQLite and reads them back. Importing one from the other would be a
cycle.
"""

from dataclasses import dataclass, field
from typing import Any


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
    deaths_by_cause: dict[str, int] = field(default_factory=dict)
    by_tribe: dict[str, int] = field(default_factory=dict)
    by_strategy: dict[str, int] = field(default_factory=dict)
    payoff_by_strategy: dict[str, float] = field(default_factory=dict)
    cooperation_by_game: dict[str, float] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
