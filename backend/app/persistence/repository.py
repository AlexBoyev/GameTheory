"""One repository over the four tables - the only SQL in the codebase.

Phase 1 wires construction and `create_tables`; the write paths land with the
features that need them (metrics in Phase 4, snapshots in Phase 6).
"""

from collections.abc import Sequence
from typing import cast

from sqlalchemy import Engine
from sqlmodel import col, select

from app.persistence.database import create_tables, session_scope
from app.persistence.models import EventRecord, MetricSample, Run, SnapshotRecord


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

    # --------------------------------------------------------------- metrics

    def add_metrics(self, sample: MetricSample) -> None:
        """Append one metrics row. Used from Phase 4."""
        with session_scope(self._engine) as session:
            session.add(sample)

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
        """Append event rows. Used from Phase 4."""
        if not records:
            return
        with session_scope(self._engine) as session:
            session.add_all(records)

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
        """Insert a snapshot and return its id. Used from Phase 6."""
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
