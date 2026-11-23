"""One repository over the four tables - the only SQL in the codebase.

Every method here is called from `RunArchive` or `SnapshotService` and from
nowhere else; services never open a session of their own.
"""

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, Engine, delete, func
from sqlmodel import col, select

from app.persistence.database import create_tables, session_scope
from app.persistence.models import EventRecord, MetricSample, Run, SnapshotRecord, utc_now


class Repository:
    """Synchronous data access; called from services, never from `sim/`."""

    __slots__ = ("_engine",)

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def initialise(self) -> None:
        """Create missing tables."""
        create_tables(self._engine)

    # ------------------------------------------------------------------ runs

    def create_run(self, seed: int, config_json: str, preset: str | None = None) -> int:
        """Insert a run row and return its id."""
        run = Run(seed=seed, config_json=config_json, preset=preset)
        with session_scope(self._engine) as session:
            session.add(run)
            session.flush()
            if run.id is None:  # pragma: no cover - set by the DB on flush
                msg = "database did not assign a run id"
                raise RuntimeError(msg)
            return run.id

    def latest_run(self) -> Run | None:
        """Return the most recently started run, if any."""
        statement = select(Run).order_by(col(Run.started_at).desc()).limit(1)
        with session_scope(self._engine) as session:
            return cast("Run | None", session.execute(statement).scalars().first())

    def end_run(self, run_id: int, last_tick: int) -> None:
        """Stamp a run as finished at `last_tick`."""
        with session_scope(self._engine) as session:
            run = session.get(Run, run_id)
            if run is None:
                return
            run.ended_at = utc_now()
            run.last_tick = last_tick
            session.add(run)

    # --------------------------------------------------------------- metrics

    def add_metrics(self, sample: MetricSample) -> None:
        """Append one metrics row."""
        with session_scope(self._engine) as session:
            session.add(sample)

    def add_metrics_many(self, samples: list[MetricSample]) -> None:
        """Append several metrics rows in one transaction.

        SQLite commits per transaction, not per row, so writing a backlog one
        row at a time costs an `fsync` each; the archive coalesces whatever
        has queued up and sends it here instead.
        """
        if not samples:
            return
        with session_scope(self._engine) as session:
            session.add_all(samples)

    def metrics_since(self, run_id: int, from_tick: int = 0) -> list[MetricSample]:
        """Return metrics rows for `run_id` at or after `from_tick`."""
        statement = (
            select(MetricSample)
            .where(MetricSample.run_id == run_id, MetricSample.tick >= from_tick)
            .order_by(col(MetricSample.tick))
        )
        with session_scope(self._engine) as session:
            rows = session.execute(statement).scalars().all()
            return list(cast("Sequence[MetricSample]", rows))

    # ---------------------------------------------------------------- events

    def add_events(self, records: list[EventRecord]) -> None:
        """Append event rows."""
        if not records:
            return
        with session_scope(self._engine) as session:
            session.add_all(records)

    def count_events(self, run_id: int) -> int:
        """How many event rows this run holds."""
        statement = (
            select(func.count()).select_from(EventRecord).where(EventRecord.run_id == run_id)
        )
        with session_scope(self._engine) as session:
            return int(session.execute(statement).scalar_one())

    def prune_events(self, run_id: int, cap: int, keep: int) -> int:
        """Trim the event log to `keep` rows once it passes `cap`.

        The table is capped rather than unbounded (SPEC section 11), and
        trimming in one jump rather than row-by-row is what keeps a long run
        at MAX speed from deleting on every insert. Returns rows removed.
        """
        if keep >= cap:
            msg = "keep must be below cap, or pruning would never settle"
            raise ValueError(msg)
        total = self.count_events(run_id)
        if total <= cap:
            return 0

        cutoff_statement = (
            select(col(EventRecord.id))
            .where(EventRecord.run_id == run_id)
            .order_by(col(EventRecord.id).desc())
            .offset(keep - 1)
            .limit(1)
        )
        with session_scope(self._engine) as session:
            cutoff = session.execute(cutoff_statement).scalars().first()
            if cutoff is None:  # pragma: no cover - only if rows vanish mid-prune
                return 0
            statement = delete(EventRecord).where(
                col(EventRecord.run_id) == run_id, col(EventRecord.id) < cutoff
            )
            result = cast("CursorResult[Any]", session.execute(statement))
            return int(result.rowcount or 0)

    def recent_events(self, run_id: int, limit: int = 100) -> list[EventRecord]:
        """Return the newest events for `run_id`, newest first."""
        statement = (
            select(EventRecord)
            .where(EventRecord.run_id == run_id)
            .order_by(col(EventRecord.tick).desc())
            .limit(limit)
        )
        with session_scope(self._engine) as session:
            rows = session.execute(statement).scalars().all()
            return list(cast("Sequence[EventRecord]", rows))

    # ------------------------------------------------------------- snapshots

    def add_snapshot(self, snapshot: SnapshotRecord) -> int:
        """Insert a snapshot and return its id."""
        with session_scope(self._engine) as session:
            session.add(snapshot)
            session.flush()
            if snapshot.id is None:  # pragma: no cover - set by the DB on flush
                msg = "database did not assign a snapshot id"
                raise RuntimeError(msg)
            return snapshot.id

    def list_snapshots(self, limit: int = 50) -> list[SnapshotRecord]:
        """Return snapshot metadata, newest first."""
        statement = (
            select(SnapshotRecord).order_by(col(SnapshotRecord.created_at).desc()).limit(limit)
        )
        with session_scope(self._engine) as session:
            rows = session.execute(statement).scalars().all()
            return list(cast("Sequence[SnapshotRecord]", rows))

    def get_snapshot(self, snapshot_id: int) -> SnapshotRecord | None:
        """Return one snapshot including its blob."""
        with session_scope(self._engine) as session:
            return session.get(SnapshotRecord, snapshot_id)
