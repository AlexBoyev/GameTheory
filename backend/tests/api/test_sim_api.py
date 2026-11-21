"""Health and the simulation control surface, end to end over HTTP."""

from fastapi.testclient import TestClient


def test_health_reports_ok_and_llm_status(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Game Theory"
    assert body["env"] == "test"
    assert body["llm"]["provider"] == "mock"
    assert body["llm"]["reachable"] is True
    assert body["llm"]["circuit_open"] is False


def test_sim_state_describes_a_real_world(client: TestClient) -> None:
    body = client.get("/api/sim/state").json()

    assert body["status"] in {"running", "paused", "stopped"}
    assert body["seed"] == 42
    assert body["population"] == 20
    assert body["placeholder"] is False, "Phase 2 runs the real engine"
    assert 0.0 <= body["time_of_day"] < 1.0
    assert body["season"] in {"spring", "summer", "autumn", "winter"}


def test_pause_then_step_advances_exactly_n_ticks(client: TestClient) -> None:
    paused = client.post("/api/sim/pause").json()
    stepped = client.post("/api/sim/step", json={"n": 5}).json()

    assert stepped["status"] == "paused"
    assert stepped["tick"] == paused["tick"] + 5


def test_start_resumes_and_pause_stops(client: TestClient) -> None:
    assert client.post("/api/sim/start").json()["status"] == "running"
    assert client.post("/api/sim/pause").json()["status"] == "paused"


def test_reset_returns_to_tick_zero(client: TestClient) -> None:
    client.post("/api/sim/step", json={"n": 3})
    reset = client.post("/api/sim/reset", json={"seed": 7}).json()

    assert reset["tick"] == 0
    assert reset["seed"] == 7
    assert reset["status"] == "paused"
    assert reset["population"] == 20


def test_speed_presets_are_accepted_and_junk_is_not(client: TestClient) -> None:
    assert client.post("/api/sim/speed", json={"multiplier": 25}).json()["speed"] == 25.0
    assert client.post("/api/sim/speed", json={"multiplier": -1}).json()["speed"] == -1.0
    assert client.post("/api/sim/speed", json={"multiplier": 0}).json()["status"] == "paused"

    rejected = client.post("/api/sim/speed", json={"multiplier": 3})
    assert rejected.status_code == 400
    assert "speed must be one of" in rejected.json()["detail"]


def test_step_rejects_zero(client: TestClient) -> None:
    assert client.post("/api/sim/step", json={"n": 0}).status_code == 422


def test_config_round_trips_and_rebuilds(client: TestClient) -> None:
    config = client.get("/api/sim/config").json()
    assert config["seed"] == 42

    config["population"] = 11
    applied = client.put("/api/sim/config", json=config)

    assert applied.status_code == 200
    assert applied.json()["population"] == 11
    assert applied.json()["tick"] == 0


def test_presets_are_listed(client: TestClient) -> None:
    presets = client.get("/api/sim/presets").json()

    assert {preset["id"] for preset in presets} >= {"peaceful_eden", "axelrod_tournament"}
    assert all(preset["name"] and preset["description"] for preset in presets)


def test_later_phases_still_announce_themselves(client: TestClient) -> None:
    response = client.get("/api/tribes")

    assert response.status_code == 501
    assert "Phase 4" in response.json()["detail"]
