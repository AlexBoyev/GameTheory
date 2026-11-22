"""What the event feed remembers.

A single ring buffer is the obvious design and it loses the interesting rows.
A busy world produces mostly gossip: at 25x speed a few hundred gossip events
arrive between two frames, so a 500-event buffer holds about twenty seconds of
chatter and nothing else. Twice while building this, a feature was reported as
broken because the event proving it worked - a god action, a spoken line - had
been pushed out by gossip before anyone looked.

So this keeps two views of the same events:

* a **chronological** buffer, which is the feed you read top to bottom;
* a **per-type** buffer, so the last N of each *kind* survive however much
  noise arrives after them. "Show me the last ten coups" then answers even if
  the coups happened ten thousand events ago.

The cost is bounded and small: one extra reference per event, and at most
`per_type * len(EventType)` of them retained.
"""

from collections import deque
from collections.abc import Iterable
from typing import Any

CHRONOLOGICAL = 500
"""How much of the raw feed to keep, newest last."""

PER_TYPE = 40
"""How many of each type to keep regardless of what arrives after them."""


class EventStore:
    """Recent events, retained both chronologically and by type."""

    __slots__ = ("_by_type", "_chronological", "_per_type")

    def __init__(self, chronological: int = CHRONOLOGICAL, per_type: int = PER_TYPE) -> None:
        self._chronological: deque[dict[str, Any]] = deque(maxlen=chronological)
        self._by_type: dict[str, deque[dict[str, Any]]] = {}
        self._per_type = per_type

    def __len__(self) -> int:
        return len(self._chronological)

    def extend(self, events: Iterable[dict[str, Any]]) -> None:
        """Record a batch of events in both views."""
        for event in events:
            self._chronological.append(event)
            kind = str(event.get("type", ""))
            bucket = self._by_type.get(kind)
            if bucket is None:
                bucket = deque(maxlen=self._per_type)
                self._by_type[kind] = bucket
            bucket.append(event)

    def clear(self) -> None:
        """Forget everything; the world was rebuilt."""
        self._chronological.clear()
        self._by_type.clear()

    def recent(self, limit: int = 100, event_type: str | None = None) -> list[dict[str, Any]]:
        """Return the newest events, newest first.

        With a type, this reads the per-type buffer - which is the whole point:
        filtering the chronological buffer would filter rows that have already
        been evicted, and quietly return nothing.
        """
        source: Iterable[dict[str, Any]]
        if event_type is None:
            source = reversed(self._chronological)
        else:
            source = reversed(self._by_type.get(event_type, deque()))
        return [event for _, event in zip(range(limit), source, strict=False)]

    def counts(self) -> dict[str, int]:
        """How many of each type are retained, for diagnostics."""
        return {kind: len(bucket) for kind, bucket in sorted(self._by_type.items())}
