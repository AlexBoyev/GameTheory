"""`WS /ws/world` - the single socket the frontend keeps open.

On connect the client gets `hello` (config, terrain meta, legends, state) and
is then fed `frame`, `events`, `metrics` and `speech` envelopes by the
simulation's broadcast loop. Client to server traffic is pings, and nothing
else.

There used to be an agent subscription here. It accepted `subscribe_agent`,
stored the id on the connection, answered `{pending: true}` - and nothing
ever read that field, so a client that followed the protocol waited for a
follow-up that could not arrive. Per-agent detail is a REST poll instead
(`GET /api/agents/{id}`, 2 Hz from the inspector), which is the cheaper
shape for it: one agent is inspected at a time, so a small request beats
widening the broadcast for every connected client. The message is still
recognised, and says so.
"""

import json
from typing import Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.ws.hub import WebSocketHub
from app.core.logging import get_logger
from app.services import envelopes
from app.services.envelopes import Envelope, MessageType
from app.services.simulation_service import SimulationService

LOG = get_logger(__name__)

router = APIRouter()

MAX_CLIENT_MESSAGE_BYTES = 4096


@router.websocket("/ws/world")
async def world_socket(websocket: WebSocket) -> None:
    """Accept a client, send `hello`, then serve broadcasts until it leaves."""
    hub = cast("WebSocketHub", websocket.app.state.hub)
    simulation = cast("SimulationService", websocket.app.state.container.simulation)

    await websocket.accept()
    connection = hub.add(websocket)
    LOG.info("ws.connected", clients=len(hub))
    try:
        await hub.send(connection, simulation.hello())
        while True:
            raw = await websocket.receive_text()
            reply = _handle_client_message(raw, simulation)
            if reply is not None:
                await hub.send(connection, reply)
    except WebSocketDisconnect:
        LOG.info("ws.disconnected", clients=len(hub) - 1)
    finally:
        hub.remove(websocket)


def _handle_client_message(raw: str, simulation: SimulationService) -> Envelope | None:
    """Parse and apply one client message, returning a reply if any."""
    if len(raw) > MAX_CLIENT_MESSAGE_BYTES:
        return envelopes.error("message too large")
    try:
        decoded: object = json.loads(raw)
    except json.JSONDecodeError:
        return envelopes.error("malformed JSON")
    if not isinstance(decoded, dict):
        return envelopes.error("expected a JSON object")
    message = cast("dict[str, Any]", decoded)

    kind = message.get("type")
    tick = simulation.state().tick
    match kind:
        case MessageType.C_PING.value:
            return Envelope(MessageType.PONG, tick)
        case MessageType.C_SUBSCRIBE_AGENT.value | MessageType.C_UNSUBSCRIBE_AGENT.value:
            # Answered rather than silently accepted: a client told "ok" by a
            # server that will never send anything is worse off than one told
            # where to look.
            return envelopes.error(
                "agent subscriptions are not served over the socket; "
                "poll GET /api/agents/{id} instead",
                tick,
            )
        case _:
            return envelopes.error(f"unknown message type: {kind!r}")
