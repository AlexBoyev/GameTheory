"""Computing and serving the time series behind the charts panel (SPEC 10).

Sampling every N ticks (not every tick) is deliberate: at MAX speed the
charts must not become the bottleneck.

Memory holds a bounded window and the `RunArchive` holds the rest. Every
sample goes to both, and `series` stitches them back together, so a long run
keeps its own beginning instead of silently losing it to the ring buffer.
"""

from collections import Counter
from typing import Any

from app.ai.gametheory.ledger import SocialLedger
from app.ai.minds import MindRegistry
from app.core.settings import Settings
from app.services.metric_point import MetricPoint
from app.services.run_archive import RunArchive
from app.sim.world import World

TRUST_EDGE_THRESHOLD = 0.25
"""Trust above which two agents count as connected, for graph density."""


SERIES_LIMIT = 2000
"""Samples kept in memory. Older ones live only in the archive."""

SERIES_TRIM = 1000
"""How many are dropped at once, so trimming is rare rather than per-sample."""


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

    __slots__ = ("_archive", "_series", "sample_every_ticks")

    def __init__(
        self,
        settings: Settings,
        archive: RunArchive | None = None,
        sample_every_ticks: int = 100,
    ) -> None:
        self._archive = archive
        self.sample_every_ticks = sample_every_ticks
        self._series: list[MetricPoint] = []
        _ = settings

    @property
    def latest(self) -> MetricPoint | None:
        """Most recent sample, if any."""
        return self._series[-1] if self._series else None

    def series(self, from_tick: int = 0) -> list[MetricPoint]:
        """Return samples at or after `from_tick`, oldest first.

        Reads through to the archive for anything the in-memory window has
        already dropped, so the charts panel shows the whole run rather than
        its most recent 2,000 samples.
        """
        live = [point for point in self._series if point.tick >= from_tick]
        if self._archive is None:
            return live
        oldest = live[0].tick if live else None
        return self._archive.history(from_tick, before_tick=oldest) + live

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
        """Append a sample to memory and to the archive.

        The in-memory list is bounded so a long run cannot grow forever; the
        archive keeps what falls off the front.
        """
        self._series.append(point)
        if len(self._series) > SERIES_LIMIT:
            del self._series[:SERIES_TRIM]
        if self._archive is not None:
            self._archive.record_metrics(point)

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
            deaths_by_cause=dict(world.deaths_by_cause),
            by_tribe=dict(by_tribe),
            by_strategy=dict(by_strategy),
            payoff_by_strategy={
                name: round(value, 3) for name, value in ledger.average_payoffs().items()
            },
            cooperation_by_game={
                game: round(rate, 4) for game, rate in ledger.cooperation_rates().items()
            },
            extra={
                # Founders have `born_tick` 0, so this is the generational
                # handover in one number: it starts at zero, and by day 18
                # it is the whole population, because nobody who washed up
                # on the island is still alive. That turn is the point of
                # the project - strategies being inherited rather than
                # merely played - and it was not visible anywhere.
                "born_here": sum(1 for agent in world.living_agents() if agent.born_tick > 0),
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
