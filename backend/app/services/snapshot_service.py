"""Save and load whole worlds as gzipped JSON (SPEC section 11).

The service owns the storage format and the database; the *world* is handed
to it by `SimulationService`, which is the only thing allowed to read the
live one safely (it holds the engine lock while doing so). Keeping those
apart means this file never has to know about threads.
"""

import gzip
import json
from dataclasses import dataclass, replace
from typing import Any

from app.persistence.models import SnapshotRecord
from app.persistence.repository import Repository


@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    """Listing row for the snapshots UI."""

    id: int
    label: str
    tick: int
    seed: int
    population: int
    created_at: str
    size_bytes: int


class SnapshotService:
    """Serialises world state to the database and back."""

    __slots__ = ("_repository",)

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    @staticmethod
    def compress(payload: dict[str, Any]) -> bytes:
        """Gzip a JSON-serialisable payload."""
        return gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    @staticmethod
    def decompress(blob: bytes) -> dict[str, Any]:
        """Inverse of `compress`."""
        decoded: dict[str, Any] = json.loads(gzip.decompress(blob).decode("utf-8"))
        return decoded

    def list_snapshots(self, limit: int = 50) -> list[SnapshotMeta]:
        """Return snapshot metadata, newest first."""
        return [
            SnapshotMeta(
                id=record.id or 0,
                label=record.label,
                tick=record.tick,
                seed=record.seed,
                population=record.population,
                created_at=record.created_at.isoformat(),
                size_bytes=record.size_bytes,
            )
            for record in self._repository.list_snapshots(limit)
        ]

    def save(self, label: str, payload: dict[str, Any]) -> SnapshotMeta:
        """Store `payload` under `label` and return its listing row."""
        blob = self.compress(payload)
        clock = payload.get("clock", {})
        agents = payload.get("agents", [])
        record = SnapshotRecord(
            label=label or f"tick {clock.get('tick', 0)}",
            tick=int(clock.get("tick", 0)),
            seed=int(payload.get("config", {}).get("seed", 0)),
            population=sum(1 for agent in agents if agent.get("alive", True)),
            size_bytes=len(blob),
            blob_gzip=blob,
        )
        # Read everything off the record *before* inserting it: once the
        # session that owns it closes, the instance is detached and touching
        # an attribute raises DetachedInstanceError rather than returning the
        # value it already had.
        meta = SnapshotMeta(
            id=0,
            label=record.label,
            tick=record.tick,
            seed=record.seed,
            population=record.population,
            created_at=record.created_at.isoformat(),
            size_bytes=record.size_bytes,
        )
        return replace(meta, id=self._repository.add_snapshot(record))

    def read(self, snapshot_id: int) -> dict[str, Any] | None:
        """Return a stored payload, or None if there is no such snapshot."""
        record = self._repository.get_snapshot(snapshot_id)
        if record is None:
            return None
        return self.decompress(record.blob_gzip)
