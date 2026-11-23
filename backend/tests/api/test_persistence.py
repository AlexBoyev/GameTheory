"""Does the running app actually write the run to disk?

The archive has its own unit tests; this asks the question those cannot,
which is whether anything calls it. The three dead features found earlier in
this project were all wired correctly in isolation and connected to nothing,
and `Repository.add_events` sat unused for six phases with a passing suite.
"""

import time
from typing import Any

from fastapi.testclient import TestClient

from app.container import Container


def settle(
    client: TestClient, container: Container, ticks: int = 60, seconds: float = 1.0
) -> Container:
    """Advance the world, let the broadcast pump drain, and flush the archive."""
    client.post("/api/sim/step", json={"n": ticks})
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        client.get("/api/sim/state")  # yields to the loop so the pump can run
        if container.archive.rows_written:
            break
        time.sleep(0.05)
    container.archive.flush(timeout_s=5.0)
    return container


def test_a_run_row_exists_as_soon_as_the_app_is_up(
    client: TestClient, container: Container
) -> None:
    container.archive.flush(timeout_s=5.0)

    run = container.repository.latest_run()
    assert run is not None, "startup never opened a run"
    assert run.seed == container.simulation.config.seed
    assert container.archive.run_id == run.id


def test_events_reach_the_database(client: TestClient, container: Container) -> None:
    settle(client, container)
    run_id = container.archive.run_id
    assert run_id is not None

    assert container.repository.count_events(run_id) > 0, (
        "the world ran and the event table is still empty"
    )


def test_a_sample_reaches_the_database(client: TestClient, container: Container) -> None:
    """Metrics sample on an elapsed-tick interval, so step past one."""
    settle(client, container, ticks=250, seconds=2.0)
    assert container.archive.run_id is not None

    stored = container.archive.history()
    assert stored, "no metrics sample was persisted"
    assert stored[0].population > 0


def test_a_reset_opens_a_second_run(client: TestClient, container: Container) -> None:
    container.archive.flush(timeout_s=5.0)
    first = container.archive.run_id

    client.post("/api/sim/reset", json={})
    container.archive.flush(timeout_s=5.0)

    assert container.archive.run_id != first, "a new world must be a new run"


def test_the_feed_reads_through_to_the_database(client: TestClient, container: Container) -> None:
    """`GET /events` tops up from SQLite rather than stopping at the ring."""
    settle(client, container)
    assert container.archive.run_id is not None

    items: list[dict[str, Any]] = client.get("/api/events?limit=50").json()["items"]

    assert items, "the feed returned nothing after a run"
    ticks = [item["tick"] for item in items]
    assert ticks == sorted(ticks, reverse=True), "newest first, from either source"
    assert len({(item["tick"], item["summary"]) for item in items}) == len(items), (
        "the same event must not appear twice when the two sources are stitched"
    )


def test_deaths_are_counted_by_cause(client: TestClient, container: Container) -> None:
    """`DeathCause` says it is "aggregated in the metrics panel" - now it is.

    Smiting is the cheapest way to produce a death with a cause known in
    advance; the tally is what SPEC section 10 asks for and what nothing
    computed before.
    """
    agents = client.get("/api/agents").json()
    victim = agents["agents"][0]["id"] if isinstance(agents, dict) else agents[0]["id"]

    assert client.post("/api/god/smite", json={"agent_id": victim}).status_code == 200
    settle(client, container, ticks=250, seconds=2.0)

    point = container.metrics.latest
    assert point is not None, "no sample was taken"
    assert point.deaths_by_cause.get("smite", 0) >= 1, point.deaths_by_cause
    assert sum(point.deaths_by_cause.values()) == point.deaths, (
        "the per-cause tally and the bare count disagree"
    )
