"""The seam between the engine thread and the event loop.

CLAUDE.md rule 3: the simulation never awaits an LLM call. So the engine
thread only ever *posts* a request and *collects* whatever has arrived since
last tick, and the event loop does the waiting. Nothing here blocks, and a
reply that arrives after its world has been reset is dropped rather than
applied to a different world.

`deque` with a `maxlen` is the back-pressure: if the model cannot keep up, the
oldest pending request is discarded, because an intention based on a situation
from thirty seconds ago is worse than no intention at all.
"""

import threading
from collections import deque
from dataclasses import dataclass

from app.ai.llm.context import PromptContext
from app.ai.llm.schemas import Intention, Reflection

MAX_PENDING = 16
MAX_DELIVERIES = 64


@dataclass(frozen=True, slots=True)
class PendingRequest:
    """A deliberation the engine thread has asked for."""

    context: PromptContext
    world_uid: int
    issued_sim_s: float


@dataclass(frozen=True, slots=True)
class Delivery:
    """A completed deliberation, waiting to be installed into a mind."""

    agent_id: int
    world_uid: int
    intention: Intention | None = None
    reflection: Reflection | None = None
    error: str | None = None
    prompt: str = ""
    response: str = ""
    """What was actually sent and received, truncated. The inspector shows
    these so "why did it do that" is answerable without reading a log."""


class IntentionBroker:
    """A two-way, thread-safe mailbox for LLM deliberations.

    Engine thread: `post` and `collect`.
    Event loop: `take_pending` and `deliver`.
    """

    __slots__ = ("_configured", "_deliveries", "_inflight", "_interval_s", "_lock", "_pending")

    def __init__(self, max_pending: int = MAX_PENDING) -> None:
        self._lock = threading.Lock()
        self._pending: deque[PendingRequest] = deque(maxlen=max_pending)
        self._deliveries: deque[Delivery] = deque(maxlen=MAX_DELIVERIES)
        self._inflight: set[int] = set()
        self._interval_s: float | None = None
        self._configured = False

    # ------------------------------------------------- the high-speed policy

    def set_interval(self, interval_s: float | None) -> None:
        """Set the sim-seconds between one agent's deliberations.

        Written by the service - the only place that knows both the engine's
        speed and the configured limits - and read by the engine thread.
        `None` means "deliberate for nobody at this speed", which is what the
        `off` high-speed policy asks for.
        """
        with self._lock:
            self._interval_s = interval_s
            self._configured = True

    def interval(self, default_s: float) -> float | None:
        """The interval to use now, or `None` to deliberate for nobody.

        Until the service has said otherwise - in a unit test, or in the first
        moments before the first broadcast - `default_s` applies.
        """
        with self._lock:
            return self._interval_s if self._configured else default_s

    # ------------------------------------------------------- engine thread

    def post(self, request: PendingRequest) -> bool:
        """Queue a request. Returns False if this agent already has one out."""
        with self._lock:
            if request.context.agent_id in self._inflight:
                return False
            self._inflight.add(request.context.agent_id)
            self._pending.append(request)
            return True

    def collect(self) -> list[Delivery]:
        """Take everything that has come back since the last call."""
        with self._lock:
            ready = list(self._deliveries)
            self._deliveries.clear()
            return ready

    def clear(self) -> None:
        """Drop everything - the world was rebuilt."""
        with self._lock:
            self._pending.clear()
            self._deliveries.clear()
            self._inflight.clear()

    # ---------------------------------------------------------- event loop

    def take_pending(self, limit: int = 4) -> list[PendingRequest]:
        """Take up to `limit` requests to work on."""
        with self._lock:
            taken: list[PendingRequest] = []
            while self._pending and len(taken) < limit:
                taken.append(self._pending.popleft())
            return taken

    def deliver(self, delivery: Delivery) -> None:
        """Hand a finished deliberation back to the engine thread."""
        with self._lock:
            self._inflight.discard(delivery.agent_id)
            self._deliveries.append(delivery)

    # ----------------------------------------------------------- observable

    @property
    def pending_count(self) -> int:
        """Requests waiting to be sent."""
        with self._lock:
            return len(self._pending)

    @property
    def inflight_count(self) -> int:
        """Agents currently waiting on a reply."""
        with self._lock:
            return len(self._inflight)
