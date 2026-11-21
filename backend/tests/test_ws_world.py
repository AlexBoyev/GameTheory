"""The world socket: `hello` on connect, then real frames."""

from typing import Any

from fastapi.testclient import TestClient

from app.sim.frames import FRAME_STRIDE, RESOURCE_STRIDE

MAX_MESSAGES = 60


def _receive_until(websocket: Any, message_type: str) -> dict[str, Any]:
    """Return the first message of `message_type`, or fail the test."""
    for _ in range(MAX_MESSAGES):
        message: dict[str, Any] = websocket.receive_json()
        if message["type"] == message_type:
            return message
    raise AssertionError(f"no {message_type!r} message within {MAX_MESSAGES} messages")


def test_hello_carries_the_world_the_client_needs(client: TestClient) -> None:
    with client.websocket_connect("/ws/world") as websocket:
        hello = websocket.receive_json()

    assert hello["type"] == "hello"
    data = hello["data"]
    assert data["config"]["seed"] == 42
    assert data["terrain"]["available"] is True, "Phase 2 serves real terrain"
    assert data["terrain"]["resolution"] > 0
    assert "wander" in data["legend"]["states"]
    assert "forest" in data["legend"]["biomes"]
    assert "berry_bush" in data["legend"]["resources"]
    assert data["state"]["population"] == 20

    nodes = data["resources"]["nodes"]
    assert data["resources"]["stride"] == RESOURCE_STRIDE
    assert nodes and len(nodes) % RESOURCE_STRIDE == 0


def test_frames_are_stride_seven_arrays_of_living_agents(client: TestClient) -> None:
    client.post("/api/sim/start")
    with client.websocket_connect("/ws/world") as websocket:
        frame = _receive_until(websocket, "frame")

    data = frame["data"]
    assert data["stride"] == FRAME_STRIDE
    assert data["agents"]
    assert len(data["agents"]) == 20 * FRAME_STRIDE
    assert 0.0 <= data["tod"] < 1.0
    assert data["season"]
    assert isinstance(data["resources"], list), "resource deltas travel with the frame"


def test_agents_actually_move(client: TestClient) -> None:
    client.post("/api/sim/start")
    with client.websocket_connect("/ws/world") as websocket:
        first = _receive_until(websocket, "frame")["data"]["agents"]
        positions = [first]
        for _ in range(12):
            positions.append(_receive_until(websocket, "frame")["data"]["agents"])

    assert any(later != first for later in positions[1:]), "the world must be alive"


def test_ping_is_answered_with_pong(client: TestClient) -> None:
    with client.websocket_connect("/ws/world") as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "ping"})
        pong = _receive_until(websocket, "pong")

    assert pong["type"] == "pong"


def test_subscribe_agent_requires_an_integer(client: TestClient) -> None:
    with client.websocket_connect("/ws/world") as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "subscribe_agent", "agent": "nope"})
        error = _receive_until(websocket, "error")

    assert "integer" in error["data"]["message"]
