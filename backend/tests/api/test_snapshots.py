"""Saving and loading worlds (SPEC section 11).

The test that matters is the round trip: a world reloaded without its
memories would look identical for one tick and then behave like a world of
strangers, which is the failure mode worth guarding against.
"""

from fastapi.testclient import TestClient


def save(client: TestClient, label: str = "test") -> dict[str, object]:
    response = client.post("/api/snapshots", json={"label": label})
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_an_empty_world_lists_no_snapshots(client: TestClient) -> None:
    assert client.get("/api/snapshots").json() == []


def test_saving_records_the_tick_the_seed_and_the_population(client: TestClient) -> None:
    client.post("/api/sim/step", json={"n": 25})
    state = client.get("/api/sim/state").json()

    meta = save(client, "after 25 ticks")

    assert meta["label"] == "after 25 ticks"
    assert meta["tick"] == state["tick"]
    assert meta["seed"] == state["seed"]
    assert meta["population"] == state["population"]
    assert int(meta["size_bytes"]) > 0


def test_an_unlabelled_snapshot_names_itself_after_its_tick(client: TestClient) -> None:
    client.post("/api/sim/step", json={"n": 10})

    assert "tick" in str(save(client, "")["label"])


def test_snapshots_are_listed_newest_first(client: TestClient) -> None:
    save(client, "first")
    client.post("/api/sim/step", json={"n": 5})
    save(client, "second")

    labels = [row["label"] for row in client.get("/api/snapshots").json()]

    assert labels[:2] == ["second", "first"]


def test_loading_restores_the_tick_and_the_population(client: TestClient) -> None:
    client.post("/api/sim/step", json={"n": 40})
    meta = save(client, "checkpoint")
    saved_tick = int(meta["tick"])
    client.post("/api/sim/step", json={"n": 40})
    assert int(client.get("/api/sim/state").json()["tick"]) > saved_tick

    response = client.post(f"/api/snapshots/{meta['id']}/load")

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    state = client.get("/api/sim/state").json()
    assert state["tick"] == saved_tick
    assert state["population"] == meta["population"]
    assert state["status"] == "paused", "a loaded world waits to be started"


def test_loading_restores_the_agents_themselves(client: TestClient) -> None:
    client.post("/api/sim/step", json={"n": 50})
    before = {
        agent["id"]: (agent["name"], agent["strategy"], round(agent["x"], 3))
        for agent in client.get("/api/agents", params={"limit": 500}).json()
    }
    meta = save(client, "people")
    client.post("/api/sim/step", json={"n": 50})

    client.post(f"/api/snapshots/{meta['id']}/load")

    after = {
        agent["id"]: (agent["name"], agent["strategy"], round(agent["x"], 3))
        for agent in client.get("/api/agents", params={"limit": 500}).json()
    }
    assert after == before


def test_loading_restores_what_agents_remember(client: TestClient) -> None:
    """Without this a reloaded world is a world of strangers."""
    client.post("/api/sim/step", json={"n": 120})
    agents = client.get("/api/agents", params={"limit": 500}).json()
    with_memory = next(
        (
            detail
            for agent in agents
            if (detail := client.get(f"/api/agents/{agent['id']}").json())["relationships"]
        ),
        None,
    )
    assert with_memory is not None, "120 ticks should produce at least one relationship"
    agent_id = with_memory["summary"]["id"]
    before = with_memory["relationships"]

    meta = save(client, "memories")
    client.post("/api/sim/step", json={"n": 60})
    client.post(f"/api/snapshots/{meta['id']}/load")

    after = client.get(f"/api/agents/{agent_id}").json()["relationships"]
    assert after == before, "trust and history must survive the round trip"


def test_loading_restores_the_resources_agents_were_using(client: TestClient) -> None:
    client.post("/api/sim/step", json={"n": 60})
    client.post("/api/god/drought", json={"x": 0.0, "z": 0.0, "radius": 500.0})
    meta = save(client, "after the drought")

    client.post("/api/sim/reset", json={})
    client.post(f"/api/snapshots/{meta['id']}/load")

    # The drought is part of the world, so it has to come back with it.
    again = client.post("/api/god/bounty", json={"x": 0.0, "z": 0.0, "radius": 500.0}).json()
    assert int(again["affected"]) > 0


def test_a_loaded_world_keeps_running_from_where_it_was(client: TestClient) -> None:
    client.post("/api/sim/step", json={"n": 40})
    meta = save(client, "resume")
    client.post(f"/api/snapshots/{meta['id']}/load")

    client.post("/api/sim/step", json={"n": 20})

    state = client.get("/api/sim/state").json()
    assert state["tick"] == int(meta["tick"]) + 20
    assert state["population"] > 0


def test_loading_an_unknown_snapshot_is_a_404(client: TestClient) -> None:
    response = client.post("/api/snapshots/4242/load")

    assert response.status_code == 404
    assert "4242" in response.json()["detail"]


def test_a_snapshot_is_smaller_than_the_terrain_it_omits(client: TestClient) -> None:
    """Terrain is regenerated from the seed rather than stored."""
    meta = save(client, "size check")

    resolution = client.get("/api/sim/config").json()["terrain"]["resolution"]
    heightmap_floats = resolution * resolution
    assert int(meta["size_bytes"]) < heightmap_floats * 4, "looks like the terrain went in"
