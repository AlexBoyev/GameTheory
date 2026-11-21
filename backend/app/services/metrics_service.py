"""Computing and serving the time series behind the charts panel (SPEC 10).

Sampling every N ticks (not every tick) is deliberate: at MAX speed the
charts must not become the bottleneck.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.ai.gametheory.ledger import SocialLedger
from app.ai.minds import MindRegistry
from app.core.settings import Settings
from app.persistence.repository import Repository
from app.sim.world import World

TRUST_EDGE_THRESHOLD = 0.25
"""Trust above which two agents count as connected, for graph density."""


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
    cooperation_by_game: dict[str, float] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


def gini(values: list[float]) -> float:
    """Return the Gini coefficient of `values`, in `[0, 1]`.

    Zero is perfect equality. This is the number that says whether the
    island has developed a rich and a poor.
    """
    positive = sorted(max(0.0, value) for value in values)
    total = sum(positive)
    if not positive or total <= 0:
        return 0.0
    count = len(positive)
    weighted = sum((index + 1) * value for index, value in enumerate(positive))
    return (2.0 * weighted) / (count * total) - (count + 1.0) / count


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

    def is_due(self, tick: int, last_sampled: int) -> bool:
        """Whether enough ticks have passed since `last_sampled`.

        Interval-based, not `tick % N == 0`: the sampler only ever sees the
        ticks that happen to land on a broadcast, and at 250 ticks a second
        those are ~12 apart, so exact multiples were missed almost every
        time and the charts stayed empty at any interesting speed.
        """
        if tick <= 0:
            return False
        return tick - last_sampled >= self.sample_every_ticks

    def record(self, point: MetricPoint) -> None:
        """Append a sample, bounding the series so a long run cannot grow forever."""
        self._series.append(point)
        if len(self._series) > 2000:
            del self._series[:1000]

    def clear(self) -> None:
        """Drop the series; the world was rebuilt."""
        self._series.clear()

    def sample(self, world: World, ledger: SocialLedger, minds: MindRegistry) -> MetricPoint:
        """Compute one sample from the live world (SPEC section 10)."""
        agents = world.living_agents()

        by_strategy: Counter[str] = Counter(agent.strategy for agent in agents)
        by_tribe: Counter[str] = Counter()
        for agent in agents:
            key = (
                "none"
                if agent.tribe_id is None
                else world.tribes[agent.tribe_id].name
                if (agent.tribe_id in world.tribes)
                else f"#{agent.tribe_id}"
            )
            by_tribe[key] += 1

        point = MetricPoint(
            tick=world.clock.tick,
            sim_seconds=round(world.clock.sim_seconds, 2),
            population=len(agents),
            births=world.births,
            deaths=world.deaths,
            cooperation_rate=round(ledger.cooperation_rate(), 4),
            food_gini=round(gini([agent.inventory.food for agent in agents]), 4),
            trust_density=round(self._trust_density(agents, minds), 4),
            by_tribe=dict(by_tribe),
            by_strategy=dict(by_strategy),
            payoff_by_strategy={
                name: round(value, 3) for name, value in ledger.average_payoffs().items()
            },
            cooperation_by_game={
                game: round(rate, 4) for game, rate in ledger.cooperation_rates().items()
            },
            extra={
                "tribes": len(world.tribes),
                "shelters": len(world.shelters),
                "betrayals": ledger.betrayals,
                "gifts": ledger.gifts,
                "lies_told": ledger.lies_told,
                "lies_caught": ledger.lies_caught,
                "attacks": ledger.attacks,
                "alliances": ledger.alliances,
                "wars": ledger.wars_declared,
                "coups_won": ledger.coups,
                "coups_tried": ledger.coup_attempts,
            },
        )
        self.record(point)
        return point

    @staticmethod
    def _trust_density(agents: list[Any], minds: MindRegistry) -> float:
        """Share of known pairings that are warm enough to call a bond."""
        known = 0
        bonded = 0
        for agent in agents:
            mind = minds.get(agent.id)
            if mind is None:
                continue
            for relationship in mind.memory.social.values():
                if relationship.interactions == 0:
                    continue
                known += 1
                if relationship.trust >= TRUST_EDGE_THRESHOLD:
                    bonded += 1
        return bonded / known if known else 0.0
