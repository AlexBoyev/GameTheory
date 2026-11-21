"""Terrain transfer, the agent endpoints and the event feed."""

import base64

import numpy as np
from fastapi.testclient import TestClient


def test_terrain_decodes_into_the_promised_arrays(client: TestClient) -> None:
    body = client.get("/api/world/terrain").json()
    resolution = body["resolution"]

    heights = np.frombuffer(base64.b64decode(body["heights_b64"]), dtype="<f4")
    biomes = np.frombuffer(base64.b64decode(body["biomes_b64"]), dtype="<u1")

    assert heights.size == resolution * resolution
    assert biomes.size == resolution * resolution
    assert heights.min() >= 0.0
    assert heights.max() <= body["max_height"] + 1e-5
    assert body["water_level"] < body["max_height"]
    assert "water" in body["biome_names"]
    assert biomes.max() < len(body["biome_names"])


def test_the_terrain_edge_is_water(client: TestClient) -> None:
    body = client.get("/api/world/terrain").json()
    resolution = body["resolution"]
    biomes = np.frombuffer(base64.b64decode(body["biomes_b64"]), dtype="<u1")
    grid = biomes.reshape((resolution, resolution))
    water = body["biome_names"].index("water")

    assert grid[0, :].max() == water
    assert grid[:, 0].max() == water


def test_agents_are_listed_with_positions_and_strategies(client: TestClient) -> None:
    agents = client.get("/api/agents").json()

    assert len(agents) == 20
    first = agents[0]
    assert first["name"]
    assert first["alive"] is True
    assert first["strategy"]
    assert first["brain_type"] in {"utility", "llm"}
    assert isinstance(first["x"], float)


def test_the_agent_limit_is_honoured(client: TestClient) -> None:
    assert len(client.get("/api/agents", params={"limit": 3}).json()) == 3


def test_agent_detail_includes_needs_traits_and_a_trace(client: TestClient) -> None:
    client.post("/api/sim/step", json={"n": 40})
    agent_id = client.get("/api/agents").json()[0]["id"]

    detail = client.get(f"/api/agents/{agent_id}").json()

    assert detail["summary"]["id"] == agent_id
    assert set(detail["needs"]) == {"hunger", "thirst", "energy", "safety", "social"}
    assert 0.0 <= detail["traits"]["honesty"] <= 1.0
    assert detail["inventory"]["food"] >= 0.0
    assert detail["life_stage"] in {"child", "adult", "elder"}
    assert detail["llm"] is None
    assert isinstance(detail["decision_trace"], list)
    assert detail["current_skill"], "after 40 ticks an agent should be doing something"


def test_an_unknown_agent_is_a_404(client: TestClient) -> None:
    response = client.get("/api/agents/9999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_the_event_feed_is_shaped_correctly_even_when_empty(client: TestClient) -> None:
    body = client.get("/api/events").json()

    assert "items" in body
    assert isinstance(body["items"], list)
    for item in body["items"]:
        assert item["type"]
        assert item["summary"]


def test_metrics_are_served_empty_until_phase_4(client: TestClient) -> None:
    body = client.get("/api/metrics").json()

    assert body["points"] == []
    assert body["sample_every_ticks"] > 0
