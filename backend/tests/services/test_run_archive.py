"""The run archive: the half of persistence that was never wired up.

SPEC sections 10 and 11 call for metrics and a capped event log in SQLite.
The tables and the repository existed from Phase 1 and nothing ever wrote to
them, so these tests are about the wiring as much as the behaviour: that a
run row appears, that samples and events reach the disk, that they come back
the way they went in, and that a database having a bad day cannot take the
simulation down with it.
"""

from pathlib import Path

import pytest

from app.core.settings import Settings
from app.persistence.database import build_engine
from app.persistence.repository import Repository
from app.services.metric_point import MetricPoint
from app.services.metrics_service import SERIES_LIMIT, MetricsService
from app.services.run_archive import RunArchive


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    """A repository over a throwaway SQLite file."""
    settings = Settings(_env_file=None, env="test", data_dir=tmp_path / "data")
    repository = Repository(build_engine(settings))
    repository.initialise()
    return repository


@pytest.fixture
def archive(repository: Repository) -> RunArchive:
    """A started archive; the writer thread is a daemon, so no teardown."""
    archive = RunArchive(repository)
    archive.start()
    return archive


def event(tick: int, kind: str = "gossip", summary: str = "said a thing") -> dict[str, object]:
    """One event in the wire form the feed builds."""
    return {
        "tick": tick,
        "type": kind,
        "summary": summary,
        "importance": 4,
        "actors": [1, 2],
        "x": 1.5,
        "z": -2.5,
    }


def point(tick: int, population: int = 10) -> MetricPoint:
    """One sample with every dict-valued field populated."""
    return MetricPoint(
        tick=tick,
        sim_seconds=tick * 0.1,
        population=population,
        births=2,
        deaths=1,
        cooperation_rate=0.75,
        food_gini=0.5,
        trust_density=0.25,
        by_tribe={"Ashfolk": 4},
        by_strategy={"TitForTat": 6},
        payoff_by_strategy={"TitForTat": 2.5},
        cooperation_by_game={"prisoners_dilemma": 0.8},
        extra={"tribes": 1.0},
    )


# ------------------------------------------------------------------- runs


def test_a_run_row_appears_when_a_world_is_born(
    archive: RunArchive, repository: Repository
) -> None:
    archive.begin(seed=1337, config_json='{"seed": 1337}')
    assert archive.flush(), "the writer did not reach the barrier"

    run = repository.latest_run()
    assert run is not None
    assert run.seed == 1337
    assert archive.run_id == run.id


def test_nothing_is_written_before_a_run_begins(
    archive: RunArchive, repository: Repository
) -> None:
    """Rows need a run to belong to; without one they are dropped, not crashed."""
    archive.record_metrics(point(tick=10))
    archive.record_events([event(tick=10)])
    assert archive.flush()

    assert repository.latest_run() is None
    assert archive.history() == []
    assert archive.past_events(limit=10) == []


def test_a_reset_starts_a_second_run(archive: RunArchive, repository: Repository) -> None:
    """Two worlds are two runs; mixing their metrics would be nonsense."""
    archive.begin(seed=1, config_json="{}")
    assert archive.flush()
    first = archive.run_id

    archive.record_metrics(point(tick=100))
    archive.begin(seed=2, config_json="{}")
    assert archive.flush()
    archive.record_metrics(point(tick=50))
    assert archive.flush()

    assert archive.run_id != first
    ticks = [sample.tick for sample in archive.history()]
    assert ticks == [50], "the new run must not inherit the old one's samples"


def test_a_run_is_closed_off_at_its_last_tick(archive: RunArchive, repository: Repository) -> None:
    archive.begin(seed=7, config_json="{}")
    archive.end(tick=4321)
    assert archive.flush()

    run = repository.latest_run()
    assert run is not None
    assert run.last_tick == 4321
    assert run.ended_at is not None


# ---------------------------------------------------------------- metrics


def test_a_sample_survives_the_round_trip(archive: RunArchive) -> None:
    """Including the dict-valued parts, which travel as JSON."""
    archive.begin(seed=1, config_json="{}")
    archive.record_metrics(point(tick=300))
    assert archive.flush()

    stored = archive.history()
    assert len(stored) == 1
    assert stored[0] == point(tick=300)


def test_history_can_stop_short_of_what_memory_still_holds(archive: RunArchive) -> None:
    """`before_tick` is what stops the two sources overlapping."""
    archive.begin(seed=1, config_json="{}")
    for tick in (100, 200, 300):
        archive.record_metrics(point(tick=tick))
    assert archive.flush()

    assert [sample.tick for sample in archive.history(before_tick=300)] == [100, 200]
    assert [sample.tick for sample in archive.history(from_tick=200)] == [200, 300]


# ----------------------------------------------------------------- events


def test_events_survive_the_round_trip(archive: RunArchive) -> None:
    archive.begin(seed=1, config_json="{}")
    archive.record_events([event(tick=5), event(tick=6, kind="betrayal", summary="stabbed")])
    assert archive.flush()

    stored = archive.past_events(limit=10)
    assert [item["tick"] for item in stored] == [6, 5], "newest first"
    assert stored[0]["type"] == "betrayal"
    assert stored[0]["actors"] == [1, 2]
    assert stored[1]["x"] == 1.5


def test_events_can_be_filtered_by_type(archive: RunArchive) -> None:
    archive.begin(seed=1, config_json="{}")
    archive.record_events(
        [event(tick=1), event(tick=2, kind="coup"), event(tick=3), event(tick=4, kind="coup")]
    )
    assert archive.flush()

    coups = archive.past_events(limit=10, event_type="coup")
    assert [item["tick"] for item in coups] == [4, 2]


def test_the_event_table_is_capped(repository: Repository) -> None:
    """SPEC section 11 says capped; an unbounded log eats the disk.

    Pruning is driven straight through the repository here rather than
    through 24,000 queued events, which would test the queue, not the cap.
    """
    archive = RunArchive(repository)
    archive.start()
    archive.begin(seed=1, config_json="{}")
    assert archive.flush()
    run_id = archive.run_id
    assert run_id is not None

    archive.record_events([event(tick=tick) for tick in range(500)])
    assert archive.flush()
    assert repository.count_events(run_id) == 500

    removed = repository.prune_events(run_id, cap=100, keep=60)

    assert removed == 440
    assert repository.count_events(run_id) == 60
    kept = archive.past_events(limit=100)
    assert kept[0]["tick"] == 499, "pruning keeps the newest"
    assert len(kept) == 60


def test_pruning_below_the_cap_does_nothing(repository: Repository) -> None:
    archive = RunArchive(repository)
    archive.start()
    archive.begin(seed=1, config_json="{}")
    archive.record_events([event(tick=tick) for tick in range(10)])
    assert archive.flush()
    assert archive.run_id is not None

    assert repository.prune_events(archive.run_id, cap=100, keep=60) == 0
    assert repository.count_events(archive.run_id) == 10


def test_a_cap_below_the_keep_is_rejected(repository: Repository) -> None:
    """Otherwise every insert would prune, forever."""
    with pytest.raises(ValueError, match="below cap"):
        repository.prune_events(1, cap=50, keep=50)


# ------------------------------------------------------------- resilience


class BrokenRepository(Repository):
    """A repository that fails every write, as a full disk would."""

    def create_run(self, seed: int, config_json: str, preset: str | None = None) -> int:
        msg = "disk on fire"
        raise RuntimeError(msg)


def test_a_failing_database_does_not_reach_the_caller(tmp_path: Path) -> None:
    """The island keeps turning; a lost chart is not a lost simulation."""
    settings = Settings(_env_file=None, env="test", data_dir=tmp_path / "data")
    broken = BrokenRepository(build_engine(settings))
    broken.initialise()
    archive = RunArchive(broken)
    archive.start()

    archive.begin(seed=1, config_json="{}")
    archive.record_metrics(point(tick=1))
    assert archive.flush(), "the writer thread must survive a failed write"
    assert archive.run_id is None


def test_the_hot_paths_never_block_on_a_stopped_writer(repository: Repository) -> None:
    """Nothing consumes the queue here; the calls must still return."""
    archive = RunArchive(repository)

    archive.begin(seed=1, config_json="{}")
    for tick in range(2000):  # far past QUEUE_SIZE
        archive.record_metrics(point(tick=tick))
        archive.record_events([event(tick=tick)])

    assert archive.run_id is None


# --------------------------------------------- stitched together with memory


def test_the_series_reads_through_to_the_archive(repository: Repository) -> None:
    """The point of the whole exercise: a long run keeps its own beginning."""
    settings = Settings(_env_file=None, env="test", data_dir=repository_path(repository))
    archive = RunArchive(repository)
    archive.start()
    archive.begin(seed=1, config_json="{}")
    metrics = MetricsService(settings, archive)

    # Flushed periodically because the queue is deliberately droppable: in a
    # real run samples arrive seconds apart, never 2,200 in a tight loop.
    for index, tick in enumerate(range(0, (SERIES_LIMIT + 200) * 10, 10)):
        metrics.record(point(tick=tick))
        if index % 128 == 0:
            assert archive.flush(timeout_s=10.0)
    assert archive.flush(timeout_s=10.0)

    series = metrics.series()
    ticks = [sample.tick for sample in series]

    assert len(metrics._series) < SERIES_LIMIT + 200, "memory should have trimmed"
    assert ticks == sorted(ticks), "stitched history must stay in order"
    assert len(ticks) == len(set(ticks)), "a sample in both places must appear once"
    assert ticks[0] == 0, "the first sample is long gone from memory"


def repository_path(repository: Repository) -> Path:
    """The data directory behind `repository` (its engine knows the URL)."""
    url = str(repository._engine.url)
    return Path(url.removeprefix("sqlite:///")).parent
