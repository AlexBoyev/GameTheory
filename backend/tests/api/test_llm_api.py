"""The LLM endpoints (SPEC section 8).

These exist so the UI can be honest about what is running - "mock provider,
Ollama not installed" rather than implying anyone is deliberating.
"""

from fastapi.testclient import TestClient


def test_status_reports_the_mock_provider(client: TestClient) -> None:
    payload = client.get("/api/llm/status").json()

    assert payload["provider"] == "mock"
    assert payload["model"] == "mock-deterministic"
    assert payload["circuit_open"] is False


def test_stats_start_empty_and_have_a_call_log(client: TestClient) -> None:
    payload = client.get("/api/llm/stats").json()

    assert payload["calls"] >= 0
    assert isinstance(payload["recent"], list)
    assert payload["failure_rate"] == 0.0 or payload["calls"] > 0


def test_deliberation_can_be_switched_off_at_runtime(client: TestClient) -> None:
    payload = client.put("/api/llm/settings", json={"enabled": False}).json()

    assert payload["enabled"] is False
    assert client.get("/api/llm/status").json()["enabled"] is False

    assert client.put("/api/llm/settings", json={"enabled": True}).json()["enabled"] is True


def test_limits_can_be_changed_at_runtime(client: TestClient) -> None:
    response = client.put(
        "/api/llm/settings",
        json={"max_agents": 4, "max_calls_per_min": 12, "high_speed_policy": "off"},
    )

    assert response.status_code == 200
    assert response.json()["max_agents"] == 4


def test_switching_to_ollama_is_reported_not_refused(client: TestClient) -> None:
    """Selecting a daemon that is not running is answered honestly.

    Refusing would be wrong: the simulation runs either way, and the UI needs
    to be able to show "ollama, unreachable" so the user can go and start it.
    """
    payload = client.put("/api/llm/settings", json={"provider": "ollama"}).json()

    assert payload["provider"] == "ollama"
    assert payload["reachable"] in (False, True)

    back = client.put("/api/llm/settings", json={"provider": "mock"}).json()
    assert back["provider"] == "mock"


def test_unknown_settings_are_rejected(client: TestClient) -> None:
    response = client.put("/api/llm/settings", json={"temperature": 2.0})

    assert response.status_code == 422


def test_limits_are_validated(client: TestClient) -> None:
    assert client.put("/api/llm/settings", json={"max_concurrency": 0}).status_code == 422
    assert client.put("/api/llm/settings", json={"timeout_s": -1}).status_code == 422
