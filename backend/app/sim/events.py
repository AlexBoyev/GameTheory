"""Simulation events and the in-engine bus that batches them for broadcast."""

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """Everything worth putting in the event feed (SPEC sections 8, 10)."""

    BIRTH = "birth"
    DEATH = "death"
    ENCOUNTER = "encounter"
    COOPERATION = "cooperation"
    DEFECTION = "defection"
    BETRAYAL = "betrayal"
    GIFT = "gift"
    TRADE = "trade"
    GOSSIP = "gossip"
    LIE_TOLD = "lie_told"
    LIE_CAUGHT = "lie_caught"
    ALLIANCE = "alliance"
    COMBAT = "combat"
    HUNT = "hunt"
    TRIBE_FOUNDED = "tribe_founded"
    TRIBE_JOINED = "tribe_joined"
    TRIBE_LEFT = "tribe_left"
    TRIBE_SPLIT = "tribe_split"
    LEADER_CHANGED = "leader_changed"
    COUP = "coup"
    WAR_DECLARED = "war_declared"
    PEACE_MADE = "peace_made"
    RAID = "raid"
    SPEECH = "speech"
    DISASTER = "disaster"
    GOD_ACTION = "god_action"


@dataclass(frozen=True, slots=True)
class SimEvent:
    """One thing that happened, at a tick, to some actors, somewhere.

    Attributes:
        tick: When it happened.
        type: Event kind, used for feed filters.
        actors: Agent ids involved, actor first.
        summary: Short human-readable line for the feed.
        importance: 1-10; drives memory retention and feed highlighting.
        position: Where the camera should fly on click, if anywhere.
        data: Type-specific extras (payoffs, resource, tribe id, ...).
    """

    tick: int
    type: EventType
    summary: str
    actors: tuple[int, ...] = ()
    importance: int = 3
    position: tuple[float, float] | None = None
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Bounded FIFO of events produced during a tick.

    The engine appends; the service layer drains once per broadcast so a slow
    or absent client can never grow memory without bound.
    """

    __slots__ = ("_dropped", "_events")

    def __init__(self, capacity: int = 4096) -> None:
        self._events: deque[SimEvent] = deque(maxlen=capacity)
        self._dropped = 0

    def __len__(self) -> int:
        return len(self._events)

    @property
    def dropped(self) -> int:
        """How many events were discarded because the buffer was full."""
        return self._dropped

    def emit(self, event: SimEvent) -> None:
        """Append `event`, counting a drop if the buffer is already full."""
        if self._events.maxlen is not None and len(self._events) == self._events.maxlen:
            self._dropped += 1
        self._events.append(event)

    def drain(self, limit: int | None = None) -> list[SimEvent]:
        """Remove and return up to `limit` buffered events (oldest first)."""
        count = len(self._events) if limit is None else min(limit, len(self._events))
        return [self._events.popleft() for _ in range(count)]
