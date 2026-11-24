"""The WebSocket hub: one place that knows about live client sockets.

The hub subscribes itself to a service's broadcast callback, so services stay
transport-agnostic and a dead socket can never break the broadcast loop.
"""

from dataclasses import dataclass, field

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.api.ws.serializer import JsonSerializer, Serializer
from app.core.logging import get_logger
from app.services.envelopes import Envelope

LOG = get_logger(__name__)


@dataclass(slots=True)
class Connection:
    """One connected client."""

    socket: WebSocket

    @property
    def is_open(self) -> bool:
        """True while the socket can still accept sends."""
        return self.socket.client_state is WebSocketState.CONNECTED


@dataclass(slots=True)
class WebSocketHub:
    """Fan-out to every connected client."""

    serializer: Serializer = field(default_factory=JsonSerializer)
    connections: dict[int, Connection] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.connections)

    def add(self, socket: WebSocket) -> Connection:
        """Register an accepted socket."""
        connection = Connection(socket=socket)
        self.connections[id(socket)] = connection
        return connection

    def remove(self, socket: WebSocket) -> None:
        """Forget a socket."""
        self.connections.pop(id(socket), None)

    def get(self, socket: WebSocket) -> Connection | None:
        """Return the connection for `socket`, if registered."""
        return self.connections.get(id(socket))

    async def send(self, connection: Connection, envelope: Envelope) -> None:
        """Send one envelope to one client."""
        payload = self.serializer.encode(envelope)
        if isinstance(payload, str):
            await connection.socket.send_text(payload)
        else:
            await connection.socket.send_bytes(payload)

    async def broadcast(self, envelope: Envelope) -> None:
        """Send `envelope` to every open client, dropping the ones that fail."""
        if not self.connections:
            return
        payload = self.serializer.encode(envelope)
        for key, connection in tuple(self.connections.items()):
            if not connection.is_open:
                self.connections.pop(key, None)
                continue
            try:
                if isinstance(payload, str):
                    await connection.socket.send_text(payload)
                else:
                    await connection.socket.send_bytes(payload)
            # One bad socket must not stop the broadcast to the others.
            except Exception as exc:
                LOG.debug("ws.send_failed", error=str(exc))
                self.connections.pop(key, None)
