"""Save and load whole worlds as gzipped JSON (SPEC section 11). Phase 6."""

import gzip
import json
from dataclasses import dataclass
from typing import Any

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

    def save(self, label: str) -> int:
        """Persist the current world. Implemented in Phase 6."""
        msg = "SnapshotService.save() arrives in Phase 6 (snapshots)"
        raise NotImplementedError(msg)

    def load(self, snapshot_id: int) -> None:
        """Restore a saved world. Implemented in Phase 6."""
        msg = "SnapshotService.load() arrives in Phase 6 (snapshots)"
        raise NotImplementedError(msg)
