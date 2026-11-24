"""The durable record of a run: its row, its metrics and its events.

SPEC sections 10 and 11 say metrics and a capped event log live in SQLite.
The tables, the models and the repository methods were all written in Phase 1
and then nothing ever called them - `EventRecord` was never once constructed,
and `MetricsService` was handed a `Repository` it never used. Charts and the
feed lived entirely in memory and died with the process.

This is the piece that was missing. It owns three things that belong
together:

* **which run we are in.** A run begins when a world is born - at startup and
  again on every reset or restore - and everything written is stamped with
  its id.
* **writing, off every hot path.** The engine thread must never touch SQL,
  and neither should the event loop: a sample lands every few seconds but a
  batch of events lands twenty times a second, and an `fsync` on the
  broadcast thread is a stutter in everybody's frame rate. So callers only
  ever put a job on a queue, and a single daemon thread does the I/O.
* **reading it back.** Memory keeps a bounded window - 2,000 samples and 500
  events - so a long run loses its own beginning. The archive is what the
  charts panel and the feed fall back to for anything older.

Failures here are logged and swallowed. A database that will not write is a
lost chart, not a lost simulation, and the island should keep turning.
"""

import json
import queue
import threading
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.persistence.models import EventRecord, MetricSample
from app.persistence.repository import Repository
from app.services.metric_point import MetricPoint

LOG = get_logger(__name__)

QUEUE_SIZE = 256
"""Pending jobs before the archive starts dropping them.

Dropping is correct: the simulation is the product and the archive is a
record of it, so a database that cannot keep up must not become back
pressure on the thing being recorded.
"""

EVENT_CAP = 20_000
"""Rows the event table keeps per run - the "capped" in SPEC section 11."""

PRUNE_TO = 15_000
"""How far down a prune cuts, so pruning is occasional rather than constant."""

HISTORY_LIMIT = 2_000
"""Archived samples a single read will return.

With the in-memory window on top of it that is up to 4,000 points behind a
chart a few hundred pixels wide, which is already far more than can be
drawn. The cap is what stops a poll every three seconds from growing into a
full-table scan as a run gets long.
"""

PRUNE_EVERY = 2_000
"""Rows written between checks, so the count query is not run per batch."""

BATCH_MAX = 64
"""Jobs coalesced into one transaction.

SQLite pays an `fsync` per transaction, so a backlog written row by row is
dramatically slower than the same rows written together - which matters
exactly when it is already behind.
"""


@dataclass(frozen=True, slots=True)
class _NewRun:
    """Start recording a new run."""

    seed: int
    config_json: str
    preset: str | None


@dataclass(frozen=True, slots=True)
class _Metrics:
    """Persist one sample."""

    point: MetricPoint


@dataclass(frozen=True, slots=True)
class _Events:
    """Persist a batch of events, in the wire form the feed already builds."""

    items: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _EndRun:
    """Close the current run off at `tick`."""

    tick: int


@dataclass(frozen=True, slots=True)
class _Barrier:
    """Set once the writer has reached this point in the queue (see `flush`)."""

    reached: threading.Event


_Job = _NewRun | _Metrics | _Events | _EndRun | _Barrier


class RunArchive:
    """Writes the current run to SQLite on its own thread, and reads it back."""

    __slots__ = ("_jobs", "_repository", "_run_id", "_since_prune", "_thread", "_written")

    def __init__(self, repository: Repository) -> None:
        self._repository = repository
        self._jobs: queue.Queue[_Job | None] = queue.Queue(maxsize=QUEUE_SIZE)
        self._thread: threading.Thread | None = None
        self._run_id: int | None = None
        self._since_prune = 0
        self._written = 0

    # ---------------------------------------------------------- lifecycle

    def start(self) -> None:
        """Begin consuming jobs."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._consume, name="run-archive", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        """Drain what is queued, then stop the thread."""
        thread = self._thread
        if thread is None:
            return
        self._thread = None
        self._jobs.put(None)
        thread.join(timeout=timeout_s)
        if thread.is_alive():  # pragma: no cover - only on a wedged database
            LOG.warning("archive.stop_timeout")

    @property
    def run_id(self) -> int | None:
        """The run being recorded, once the writer has created its row."""
        return self._run_id

    @property
    def rows_written(self) -> int:
        """Event rows written since the process started (diagnostics, tests)."""
        return self._written

    def flush(self, timeout_s: float = 2.0) -> bool:
        """Block until everything queued so far has been written.

        For tests and shutdown only; the hot paths never wait for the disk.
        Works by queueing a barrier and waiting for the writer to reach it,
        rather than watching the queue empty - an empty queue only means the
        last job was picked up, not that it landed. Returns whether the
        barrier was reached before `timeout_s`.
        """
        if self._thread is None:
            return True
        reached = threading.Event()
        try:
            # Blocking, not `_submit`: a dropped barrier would report failure
            # for a writer that is merely busy, and nothing on a hot path is
            # waiting here anyway.
            self._jobs.put(_Barrier(reached=reached), timeout=timeout_s)
        except queue.Full:  # pragma: no cover - a writer this stuck is broken
            return False
        return reached.wait(timeout_s)

    # ------------------------------------------------------- hot-path API

    def begin(self, seed: int, config_json: str, preset: str | None = None) -> None:
        """Record that a new world was born."""
        self._submit(_NewRun(seed=seed, config_json=config_json, preset=preset))

    def end(self, tick: int) -> None:
        """Close the current run off, so a resumed database reads sensibly.

        Unguarded: whether a run exists is the writer thread's business, and
        asking here races with the `begin` that is probably still queued.
        """
        self._submit(_EndRun(tick=tick))

    def record_metrics(self, point: MetricPoint) -> None:
        """Queue one sample. Never blocks."""
        self._submit(_Metrics(point=point))

    def record_events(self, items: list[dict[str, Any]]) -> None:
        """Queue a batch of events in wire form. Never blocks."""
        if items:
            self._submit(_Events(items=tuple(items)))

    def _submit(self, job: _Job) -> None:
        """Queue `job`, dropping it if the writer has fallen behind."""
        try:
            self._jobs.put_nowait(job)
        except queue.Full:
            LOG.debug("archive.dropped", job=type(job).__name__)

    # ----------------------------------------------------------- read-back

    def history(self, from_tick: int = 0, before_tick: int | None = None) -> list[MetricPoint]:
        """Persisted samples for this run, oldest first.

        `before_tick` asks only for what memory no longer holds, so the two
        sources concatenate instead of overlapping.
        """
        if self._run_id is None:
            return []
        try:
            rows = self._repository.metrics_window(
                self._run_id, from_tick, before_tick, HISTORY_LIMIT
            )
        except Exception as error:  # pragma: no cover - database trouble
            LOG.warning("archive.history_failed", error=str(error))
            return []
        return [_point_from_row(row) for row in rows]

    def past_events(self, limit: int, event_type: str | None = None) -> list[dict[str, Any]]:
        """Persisted events for this run, newest first."""
        if self._run_id is None or limit < 1:
            return []
        try:
            # Over-fetch when filtering: the filter is applied here, and the
            # query is capped either way.
            over_fetch = limit if event_type is None else limit * 10
            rows = self._repository.recent_events(self._run_id, over_fetch)
        except Exception as error:  # pragma: no cover - database trouble
            LOG.warning("archive.events_failed", error=str(error))
            return []
        items = [_event_from_row(row) for row in rows]
        if event_type is not None:
            items = [item for item in items if item["type"] == event_type]
        return items[:limit]

    # -------------------------------------------------------- writer thread

    def _consume(self) -> None:
        """Drain the queue until the sentinel arrives, writing in batches."""
        while True:
            first = self._jobs.get()
            if first is None:
                return
            batch = [first]
            while len(batch) < BATCH_MAX:
                try:
                    nxt = self._jobs.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:
                    self._write_batch(batch)
                    return
                batch.append(nxt)
            self._write_batch(batch)

    def _write_batch(self, batch: list[_Job]) -> None:
        """Apply a run of jobs, coalescing neighbouring samples into one write.

        Order is preserved: samples accumulate only until a job of another
        kind arrives, so a `begin` or an `end` never overtakes the rows it
        bounds.
        """
        pending: list[MetricSample] = []
        for job in batch:
            try:
                if isinstance(job, _Metrics):
                    if self._run_id is not None:
                        pending.append(_row_from_point(self._run_id, job.point))
                    continue
                self._flush_pending(pending)
                self._apply(job)
            # A broken archive must not take the simulation with it.
            except Exception as error:
                LOG.warning("archive.write_failed", job=type(job).__name__, error=str(error))
        try:
            self._flush_pending(pending)
        except Exception as error:
            LOG.warning("archive.write_failed", job="metrics", error=str(error))

    def _flush_pending(self, pending: list[MetricSample]) -> None:
        """Write and clear whatever samples have accumulated.

        The run's `last_tick` rides along with the write, so the row says how
        far the run actually got even when the process is killed rather than
        shut down - which, with the driver's `taskkill /F`, is every time.
        """
        if not pending:
            return
        self._repository.add_metrics_many(pending)
        if self._run_id is not None:
            self._repository.touch_run(self._run_id, pending[-1].tick)
        pending.clear()

    def _apply(self, job: _Job) -> None:
        """Perform one job's write."""
        match job:
            case _Metrics(point=point):  # pragma: no cover - batched in _write_batch
                if self._run_id is not None:
                    self._repository.add_metrics(_row_from_point(self._run_id, point))
            case _NewRun(seed=seed, config_json=config_json, preset=preset):
                self._run_id = self._repository.create_run(seed, config_json, preset)
                self._since_prune = 0
                LOG.info("archive.run_started", run_id=self._run_id, seed=seed)
            case _EndRun(tick=tick):
                if self._run_id is not None:
                    self._repository.end_run(self._run_id, last_tick=tick)
            case _Events(items=items):
                if self._run_id is not None:
                    self._write_events(self._run_id, items)
            case _Barrier(reached=reached):
                reached.set()

    def _write_events(self, run_id: int, items: tuple[dict[str, Any], ...]) -> None:
        """Insert a batch and prune the table if it has grown past the cap."""
        self._repository.add_events([_row_from_event(run_id, item) for item in items])
        self._written += len(items)
        self._since_prune += len(items)
        if self._since_prune < PRUNE_EVERY:
            return
        self._since_prune = 0
        removed = self._repository.prune_events(run_id, cap=EVENT_CAP, keep=PRUNE_TO)
        if removed:
            LOG.debug("archive.pruned", run_id=run_id, removed=removed)


def _row_from_point(run_id: int, point: MetricPoint) -> MetricSample:
    """Map a sample to its row, with the dict-valued parts as JSON."""
    return MetricSample(
        run_id=run_id,
        tick=point.tick,
        sim_seconds=point.sim_seconds,
        population=point.population,
        births=point.births,
        deaths=point.deaths,
        cooperation_rate=point.cooperation_rate,
        food_gini=point.food_gini,
        trust_density=point.trust_density,
        payload_json=json.dumps(
            {
                "deaths_by_cause": point.deaths_by_cause,
                "by_tribe": point.by_tribe,
                "by_strategy": point.by_strategy,
                "payoff_by_strategy": point.payoff_by_strategy,
                "cooperation_by_game": point.cooperation_by_game,
                "extra": point.extra,
            }
        ),
    )


def _point_from_row(row: MetricSample) -> MetricPoint:
    """Map a row back to a sample."""
    try:
        payload = json.loads(row.payload_json)
    except ValueError:  # pragma: no cover - only a hand-edited database
        payload = {}
    return MetricPoint(
        tick=row.tick,
        sim_seconds=row.sim_seconds,
        population=row.population,
        births=row.births,
        deaths=row.deaths,
        cooperation_rate=row.cooperation_rate,
        food_gini=row.food_gini,
        trust_density=row.trust_density,
        deaths_by_cause=payload.get("deaths_by_cause", {}),
        by_tribe=payload.get("by_tribe", {}),
        by_strategy=payload.get("by_strategy", {}),
        payoff_by_strategy=payload.get("payoff_by_strategy", {}),
        cooperation_by_game=payload.get("cooperation_by_game", {}),
        extra=payload.get("extra", {}),
    )


def _row_from_event(run_id: int, item: dict[str, Any]) -> EventRecord:
    """Map one wire-form event to its row."""
    return EventRecord(
        run_id=run_id,
        tick=int(item["tick"]),
        type=str(item["type"]),
        summary=str(item.get("summary", "")),
        importance=int(item.get("importance", 3)),
        actors_json=json.dumps(list(item.get("actors", ()))),
        x=item.get("x"),
        z=item.get("z"),
    )


def _event_from_row(row: EventRecord) -> dict[str, Any]:
    """Map one row back to the wire form the feed already speaks."""
    try:
        actors = json.loads(row.actors_json)
    except ValueError:  # pragma: no cover - only a hand-edited database
        actors = []
    return {
        "tick": row.tick,
        "type": row.type,
        "summary": row.summary,
        "importance": row.importance,
        "actors": actors,
        "x": row.x,
        "z": row.z,
    }
