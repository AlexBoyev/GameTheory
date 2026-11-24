"""WebSocket payloads (SPEC section 8).

Services build plain `Envelope`s; `api/ws` serialises them. That keeps the
service layer free of transport concerns and lets the serialiser change
(JSON now, msgpack later) without touching the producers.

The wire codes themselves live in `sim.frames`, next to the encoder that
produces them, so there is exactly one definition of "state 4 means eating".
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.sim.frames import (
    AGENT_STATE_CODES,
    BIOME_CODES,
    FRAME_STRIDE,
    RESOURCE_CODES,
    RESOURCE_STRIDE,
)

__all__ = [
    "AGENT_STATE_CODES",
    "BIOME_CODES",
    "FRAME_STRIDE",
    "RESOURCE_CODES",
    "RESOURCE_STRIDE",
    "Envelope",
    "MessageType",
    "error",
    "events",
    "frame",
    "hello",
    "metrics",
    "speech",
]


class MessageType(StrEnum):
    """Envelope types. Client to server types are prefixed with `C_`."""

    HELLO = "hello"
    FRAME = "frame"
    EVENTS = "events"
    METRICS = "metrics"
    SPEECH = "speech"
    STATE = "state"
    ERROR = "error"
    PONG = "pong"

    C_PING = "ping"

    # Recognised only so the server can say it does not serve them; see
    # `api/ws/routes.py`.
    C_SUBSCRIBE_AGENT = "subscribe_agent"
    C_UNSUBSCRIBE_AGENT = "unsubscribe_agent"


@dataclass(frozen=True, slots=True)
class Envelope:
    """A typed message: `{type, tick, data}`."""

    type: MessageType
    tick: int = 0
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return the wire representation."""
        return {"type": self.type.value, "tick": self.tick, "data": self.data}


def hello(tick: int, payload: dict[str, Any]) -> Envelope:
    """Build the `hello` envelope sent on connect."""
    return Envelope(MessageType.HELLO, tick, payload)


def frame(tick: int, agents: list[float], time_of_day: float, **extra: object) -> Envelope:
    """Build a `frame` envelope from a flat, stride-7 agent array."""
    return Envelope(
        MessageType.FRAME,
        tick,
        {"stride": FRAME_STRIDE, "agents": agents, "tod": round(time_of_day, 4), **extra},
    )


def events(tick: int, items: list[dict[str, Any]]) -> Envelope:
    """Build a batched `events` envelope."""
    return Envelope(MessageType.EVENTS, tick, {"items": items})


def metrics(tick: int, payload: dict[str, Any]) -> Envelope:
    """Build a `metrics` envelope."""
    return Envelope(MessageType.METRICS, tick, payload)


def speech(tick: int, agent_id: int, text: str, ttl_s: float = 6.0) -> Envelope:
    """Build a `speech` envelope for a bubble above an agent's head."""
    return Envelope(MessageType.SPEECH, tick, {"agent": agent_id, "text": text, "ttl": ttl_s})


def error(message: str, tick: int = 0) -> Envelope:
    """Build an `error` envelope."""
    return Envelope(MessageType.ERROR, tick, {"message": message})
