"""Metrics sampling and the numbers behind the charts (SPEC section 10)."""

import pytest

from app.ai.gametheory.ledger import SocialLedger
from app.ai.minds import MindRegistry
from app.core.settings import Settings
from app.services.metric_point import MetricPoint
from app.services.metrics_service import MetricsService, gini
from app.sim.world import World


def service(settings: Settings, every: int = 100) -> MetricsService:
    """A metrics service with a known sampling interval."""
    return MetricsService(settings, archive=None, sample_every_ticks=every)


def test_gini_is_zero_when_everyone_has_the_same() -> None:
    assert gini([5.0, 5.0, 5.0, 5.0]) == pytest.approx(0.0, abs=1e-9)


def test_gini_approaches_one_when_one_agent_has_everything() -> None:
    assert gini([0.0, 0.0, 0.0, 100.0]) > 0.7


def test_gini_handles_an_empty_or_destitute_world() -> None:
    assert gini([]) == 0.0
    assert gini([0.0, 0.0]) == 0.0


def test_sampling_is_due_on_elapsed_ticks_not_exact_multiples(settings: Settings) -> None:
    """The bug this guards: at speed, frames skip over the exact multiples.

    The sampler only gets asked at broadcast time, so being due has to mean
    "enough ticks have passed", never "the tick divides by 100".
    """
    metrics = service(settings, every=100)

    assert not metrics.is_due(0, -1), "tick zero is the untouched world"
    assert not metrics.is_due(50, 0), "too soon"
    assert metrics.is_due(112, 0), "a full window has passed, and 112 is not a multiple of 100"
    assert not metrics.is_due(150, 112), "only 38 ticks since the last sample"
    assert metrics.is_due(213, 112)


def test_a_fast_world_still_gets_regular_samples(settings: Settings) -> None:
    """20 Hz broadcasts over a world running at ~250 ticks/second.

    Twelve ticks between frames means exact multiples of 100 are hit about
    one time in eight; this is the scenario that produced one sample in 6244
    ticks before the fix.
    """
    metrics = service(settings, every=100)
    last = -1
    samples = 0

    for frame in range(100):
        tick = frame * 12
        if metrics.is_due(tick, last):
            last = tick
            samples += 1

    assert samples >= 10, f"expected ~one sample per 100 ticks over 1200 ticks, got {samples}"


def test_slow_worlds_sample_on_the_interval(settings: Settings) -> None:
    """At 1x every tick is seen, so sampling must not fire more than once a window."""
    metrics = service(settings, every=100)
    last = -1
    ticks = [tick for tick in range(1, 501) if metrics.is_due(tick, last) and (last := tick)]

    assert ticks == [99, 199, 299, 399, 499]


def test_the_series_is_bounded(settings: Settings) -> None:
    metrics = service(settings)
    for tick in range(2500):
        metrics.record(MetricPoint(tick=tick, sim_seconds=float(tick), population=1))

    assert len(metrics.series()) <= 2000, "a long run must not grow without bound"
    assert metrics.latest is not None
    assert metrics.latest.tick == 2499


def test_series_can_be_read_from_a_tick(settings: Settings) -> None:
    metrics = service(settings)
    for tick in (100, 200, 300):
        metrics.record(MetricPoint(tick=tick, sim_seconds=float(tick), population=5))

    assert [point.tick for point in metrics.series(from_tick=200)] == [200, 300]
    assert metrics.series(from_tick=9999) == []


def test_clear_drops_the_series_for_a_rebuilt_world(settings: Settings) -> None:
    metrics = service(settings)
    metrics.record(MetricPoint(tick=100, sim_seconds=1.0, population=5))

    metrics.clear()

    assert metrics.series() == []
    assert metrics.latest is None


def test_born_here_separates_the_founders_from_their_children(
    settings: Settings, world: World
) -> None:
    """The generational handover, which was not visible anywhere before.

    Founders arrive with `born_tick` 0. By about day 18 none of them is
    alive, so this number becomes the whole population - and that turn is
    the point of the project, strategies being inherited rather than
    merely played.
    """
    first, second = world.living_agents()[:2]
    assert first.born_tick == 0, "the founding cast arrives at tick 0"
    second.born_tick = 5_000

    point = service(settings).sample(world, SocialLedger(), MindRegistry())

    assert point.extra["born_here"] == 1
