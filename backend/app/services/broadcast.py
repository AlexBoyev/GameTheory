"""Turning engine output into envelopes, and fanning them out.

Two threads meet here, which is the whole reason this is its own class:

* the **engine thread** calls `accept_frame` and `accept_events`, which only
  ever put something on a bounded queue - never blocking, never awaiting, and
  never touching asyncio;
* the **event loop** runs `run()`, which drains those queues at the broadcast
  rate and sends envelopes to every subscriber.

What it deliberately does *not* own is anything that happens to be triggered
by a frame or a batch. Metrics sampling and the LLM speed policy both run once
per frame, and the archive wants a copy of every event, but none of that is
broadcasting - they are policies belonging to `SimulationService`, handed in
as `on_frame` and `on_events`. Keeping them out is what lets this file be
about one thing and be tested without an engine or a database.
"""

import asyncio
import queue
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from app.core.logging import get_logger
from app.services import envelopes
from app.services.envelopes import Envelope
from app.services.event_store import EventStore
from app.sim.events import EventType, SimEvent
from app.sim.frames import WorldFrame

LOG = get_logger(__name__)

Subscriber = Callable[[Envelope], Awaitable[None]]
FrameHook = Callable[[WorldFrame], Awaitable[None]]
EventsHook = Callable[[list[dict[str, Any]]], None]
"""Called with every batch the feed builds. Synchronous and must not block."""

FRAME_QUEUE_SIZE = 2
"""Keep the newest frames only: a slow client must not delay the engine."""

EVENT_QUEUE_SIZE = 64


class BroadcastPump:
    """Drains the engine's output queues and broadcasts at a fixed rate."""

    __slots__ = (
        "_events",
        "_frames",
        "_interval",
        "_last_amounts",
        "_on_events",
        "_on_frame",
        "_store",
        "_subscribers",
        "_task",
    )

    def __init__(
        self,
        broadcast_hz: float,
        on_frame: FrameHook | None = None,
        on_events: EventsHook | None = None,
    ) -> None:
        self._interval = 1.0 / max(1.0, broadcast_hz)
        self._on_frame = on_frame
        self._on_events = on_events
        self._frames: queue.Queue[WorldFrame] = queue.Queue(maxsize=FRAME_QUEUE_SIZE)
        self._events: queue.Queue[list[SimEvent]] = queue.Queue(maxsize=EVENT_QUEUE_SIZE)
        self._store = EventStore()
        self._last_amounts: dict[int, float] = {}
        self._subscribers: set[Subscriber] = set()
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------- engine thread

    def accept_frame(self, frame: WorldFrame) -> None:
        """Queue a frame, dropping the stale one if the queue is full.

        Dropping the *old* frame rather than the new one is the point: a
        client that falls behind should see the present, not a backlog of the
        past.
        """
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            with suppress(queue.Empty):
                self._frames.get_nowait()
            with suppress(queue.Full):
                self._frames.put_nowait(frame)

    def accept_events(self, batch: list[SimEvent]) -> None:
        """Queue a batch of events."""
        try:
            self._events.put_nowait(batch)
        except queue.Full:
            LOG.debug("events.dropped", count=len(batch))

    # ---------------------------------------------------------- lifecycle

    def start(self) -> None:
        """Run the pump as a background task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run(), name="sim-broadcast")

    async def stop(self) -> None:
        """Cancel the pump and wait for it to finish."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    @property
    def running(self) -> bool:
        """Whether the background task is alive."""
        return self._task is not None and not self._task.done()

    def clear(self) -> None:
        """Forget per-world state; the world was rebuilt."""
        self._last_amounts.clear()
        self._store.clear()

    # ------------------------------------------------------------ pub/sub

    def subscribe(self, subscriber: Subscriber) -> None:
        """Register an async callback that receives every envelope."""
        self._subscribers.add(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        """Remove a previously registered callback."""
        self._subscribers.discard(subscriber)

    @property
    def subscriber_count(self) -> int:
        """How many transports are currently attached."""
        return len(self._subscribers)

    async def broadcast(self, envelope: Envelope) -> None:
        """Send `envelope` to every subscriber, dropping ones that fail."""
        for subscriber in tuple(self._subscribers):
            try:
                await subscriber(envelope)
            # A failing subscriber must never stop the broadcast loop.
            except Exception as error:
                LOG.warning("broadcast.subscriber_failed", error=str(error))
                self._subscribers.discard(subscriber)

    # --------------------------------------------------------------- feed

    def recent_events(
        self, limit: int = 100, event_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Return the newest events, newest first, optionally filtered."""
        return self._store.recent(limit=limit, event_type=event_type)

    # --------------------------------------------------------------- loop

    async def run(self) -> None:
        """Drain engine output and broadcast it at the configured rate."""
        while True:
            await asyncio.sleep(self._interval)
            frame = self._latest_frame()
            if frame is not None:
                await self.broadcast(self._frame_envelope(frame))
                if self._on_frame is not None:
                    await self._on_frame(frame)
            await self._drain_events()

    def _latest_frame(self) -> WorldFrame | None:
        """Return the newest queued frame, discarding anything older."""
        newest: WorldFrame | None = None
        while True:
            try:
                newest = self._frames.get_nowait()
            except queue.Empty:
                return newest

    def _frame_envelope(self, frame: WorldFrame) -> Envelope:
        """Build a frame envelope, sending resource amounts as deltas."""
        changed: list[float] = []
        for node_id, fullness in frame.resource_fullness.items():
            if self._last_amounts.get(node_id) != fullness:
                changed.extend((float(node_id), fullness))
        gone = self._last_amounts.keys() - frame.resource_fullness.keys()
        removed = [float(node_id) for node_id in sorted(gone)]
        self._last_amounts = frame.resource_fullness

        return envelopes.frame(
            frame.tick,
            frame.agents,
            frame.time_of_day,
            status=frame.status,
            speed=frame.speed,
            day=frame.day,
            season=frame.season,
            population=frame.population,
            skip=frame.skip_remaining,
            resources=changed,
            removed=removed,
        )

    async def _drain_events(self) -> None:
        """Broadcast and remember every queued event batch."""
        while True:
            try:
                batch = self._events.get_nowait()
            except queue.Empty:
                return
            items = [event_dict(event) for event in batch]
            self._store.extend(items)
            if items and self._on_events is not None:
                self._on_events(items)
            if items:
                await self.broadcast(envelopes.events(items[-1]["tick"], items))
            await self._broadcast_speech(batch)

    async def _broadcast_speech(self, batch: list[SimEvent]) -> None:
        """Send what was said as its own envelope, as well as an event.

        Speech is in the event feed because it is part of the story, and on
        its own channel because the scene needs it separately: a bubble has to
        appear over the right head and expire on its own timer, which the feed
        knows nothing about.
        """
        for event in batch:
            if event.type is not EventType.SPEECH:
                continue
            text = event.data.get("text")
            if not isinstance(text, str) or not text or not event.actors:
                continue
            await self.broadcast(envelopes.speech(event.tick, event.actors[0], text))


def event_dict(event: SimEvent) -> dict[str, Any]:
    """Return the wire form of one event."""
    return {
        "tick": event.tick,
        "type": event.type.value,
        "summary": event.summary,
        "importance": event.importance,
        "actors": list(event.actors),
        "x": None if event.position is None else round(event.position[0], 2),
        "z": None if event.position is None else round(event.position[1], 2),
    }
