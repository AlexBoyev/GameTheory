"""Serialiser seam: JSON today, msgpack later (SPEC section 8)."""

import json
from typing import Protocol

from app.services.envelopes import Envelope


class Serializer(Protocol):
    """Turns an envelope into something a WebSocket can send."""

    text_mode: bool
    """True when `encode` returns text, False for binary frames."""

    def encode(self, envelope: Envelope) -> str | bytes:
        """Encode `envelope` for the wire."""
        ...


class JsonSerializer:
    """Compact JSON, no whitespace."""

    text_mode = True

    __slots__ = ()

    def encode(self, envelope: Envelope) -> str | bytes:
        """Encode `envelope` as compact JSON text."""
        return json.dumps(envelope.as_dict(), separators=(",", ":"))
