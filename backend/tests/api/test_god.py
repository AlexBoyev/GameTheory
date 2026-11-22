"""God tools (SPEC section 9.4), through the real engine thread.

These go through the HTTP endpoint on purpose: the interesting part is not
what each tool computes but that it is applied *between ticks*, under the
engine lock, with the response describing what actually happened.
"""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import wait_until


def god(client: TestClient, action: str, **payload: Any) -> dict[str, Any]:
    """Call one god tool and return its result."""
    response = client.post(f"/api/god/{action}", json=payload)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def events(client: TestClient, kind: str = "god_action") -> list[dict[str, Any]]:
    """Events of one type from the feed."""
    items: list[dict[str, Any]] = client.get(
        "/api/events", params={"limit": 200, "type": kind}
    ).json()["items"]
    return items


# ------------------------------------------------------------------ the feed


def test_an_intervention_is_recorded_in_the_feed(client: TestClient) -> None:
    """A world that silently changed under you makes the feed a liar.

    Waited for rather than asserted outright: the engine batches events onto
    the broadcast cadence, so the feed is up to one frame behind the call -
    which is also why a *paused* world has to flush them at all (it did not,
    until this test).
    """
    before = len(events(client))

    god(client, "drop_food", x=0.0, z=0.0, amount=40.0)

    assert wait_until(lambda: len(events(client)) > before), "the feed never heard about it"
    newest = events(client)[0]
    assert newest["type"] == "god_action"
    assert "food" in str(newest["summary"]).lower()


# --------------------------------------------------------------- drop_food


def test_dropping_food_adds_resources_where_you_asked(client: TestClient) -> None:
    result = god(client, "drop_food", x=5.0, z=-5.0, amount=40.0, radius=10.0)

    assert result["affected"] == 5, "40 food in 8-food bushes"
    assert "bushes" in str(result["detail"])


def test_dropping_food_defaults_to_the_middle_of_the_island(client: TestClient) -> None:
    result = god(client, "drop_food")

    assert int(result["affected"]) > 0


# ------------------------------------------------------------------ drought


def test_a_drought_dries_up_water_that_was_infinite(client: TestClient) -> None:
    """Water is the one resource agents never plan around - until this."""
    result = god(client, "drought", x=0.0, z=0.0, radius=400.0)

    assert int(result["affected"]) > 0, "the island should have watering spots"
    assert "dried up" in str(result["detail"])

    # A second drought over the same ground finds the same nodes, now empty.
    again = god(client, "drought", x=0.0, z=0.0, radius=400.0)
    assert int(again["affected"]) == int(result["affected"])


# ------------------------------------------------------------------- bounty


def test_a_bounty_refills_the_patches_it_covers(client: TestClient) -> None:
    result = god(client, "bounty", x=0.0, z=0.0, radius=400.0)

    assert int(result["affected"]) > 0
    assert "refilled" in str(result["detail"])


# ------------------------------------------------------------------- plague


def test_a_plague_hurts_everyone_nearby_without_emptying_the_island(
    client: TestClient,
) -> None:
    """Survivable for the healthy: it should reshape a society, not end it."""
    before = int(client.get("/api/sim/state").json()["population"])

    result = god(client, "plague", x=0.0, z=0.0, radius=400.0, amount=10.0)

    assert int(result["affected"]) > 0
    after = int(client.get("/api/sim/state").json()["population"])
    assert after == before, "10 damage should not kill a healthy agent"


def test_a_severe_enough_plague_kills(client: TestClient) -> None:
    before = int(client.get("/api/sim/state").json()["population"])

    result = god(client, "plague", x=0.0, z=0.0, radius=400.0, amount=500.0)

    assert int(result["affected"]) == before
    assert int(client.get("/api/sim/state").json()["population"]) == 0
    assert "died" in str(result["detail"])


# -------------------------------------------------------------- spawn_agent


def test_spawning_adds_a_living_agent_with_the_strategy_you_chose(
    client: TestClient,
) -> None:
    before = int(client.get("/api/sim/state").json()["population"])

    result = god(client, "spawn_agent", x=1.0, z=2.0, strategy="Grudger", brain_type="llm")

    assert result["affected"] == 1
    assert "Grudger" in str(result["detail"])
    assert int(client.get("/api/sim/state").json()["population"]) == before + 1

    newest = max(client.get("/api/agents", params={"limit": 500}).json(), key=lambda a: a["id"])
    assert newest["strategy"] == "Grudger"
    assert newest["brain_type"] == "llm"


def test_a_spawned_agent_can_think(client: TestClient) -> None:
    """Without a mind it could not perceive, decide or remember anything."""
    god(client, "spawn_agent", x=0.0, z=0.0, strategy="TitForTat")
    newest = max(client.get("/api/agents", params={"limit": 500}).json(), key=lambda a: a["id"])

    client.post("/api/sim/step", json={"n": 30})

    detail = client.get(f"/api/agents/{newest['id']}").json()
    assert detail["current_skill"], "a spawned agent should get on with something"


def test_an_unknown_strategy_falls_back_rather_than_failing(client: TestClient) -> None:
    """An agent playing a strategy the engine has never heard of cannot act."""
    result = god(client, "spawn_agent", strategy="Telepathy")

    assert result["affected"] == 1
    assert "TitForTat" in str(result["detail"])


# -------------------------------------------------------------------- smite


def test_smiting_kills_the_named_agent(client: TestClient) -> None:
    agent_id = client.get("/api/agents").json()[0]["id"]
    before = int(client.get("/api/sim/state").json()["population"])

    result = god(client, "smite", agent_id=agent_id)

    assert result["affected"] == 1
    assert int(client.get("/api/sim/state").json()["population"]) == before - 1
    assert client.get(f"/api/agents/{agent_id}").json()["summary"]["alive"] is False


def test_smiting_nobody_is_reported_not_crashed(client: TestClient) -> None:
    result = god(client, "smite", agent_id=999999)

    assert result["affected"] == 0
    assert "no such living agent" in str(result["detail"])


def test_smiting_the_same_agent_twice_only_counts_once(client: TestClient) -> None:
    agent_id = client.get("/api/agents").json()[0]["id"]
    god(client, "smite", agent_id=agent_id)

    assert god(client, "smite", agent_id=agent_id)["affected"] == 0


# --------------------------------------------------------------- validation


def test_an_unknown_action_is_a_422(client: TestClient) -> None:
    """The action is an enum in the path, so FastAPI rejects it for us."""
    assert client.post("/api/god/bless", json={}).status_code == 422


def test_an_unknown_field_is_rejected(client: TestClient) -> None:
    assert client.post("/api/god/drop_food", json={"when": "now"}).status_code == 422


def test_a_negative_radius_is_rejected(client: TestClient) -> None:
    assert client.post("/api/god/plague", json={"radius": -1.0}).status_code == 422


def test_interventions_survive_a_running_world(client: TestClient) -> None:
    """The tools run between ticks, so a running engine must not race them."""
    client.post("/api/sim/start")
    try:
        for _ in range(5):
            assert int(god(client, "drop_food", amount=16.0)["affected"]) == 2
    finally:
        client.post("/api/sim/pause")
