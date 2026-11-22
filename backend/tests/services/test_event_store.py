"""What the feed remembers (and the bug that motivated it).

A single ring buffer loses the interesting rows: a busy world is mostly
gossip, so the one god action or spoken line you went looking for has already
been evicted. Twice during this build that made a working feature look broken.
"""

from app.services.event_store import EventStore


def event(kind: str, tick: int) -> dict[str, object]:
    """One wire-shaped event."""
    return {"tick": tick, "type": kind, "summary": f"{kind} at {tick}", "importance": 3}


def noise(count: int, start: int = 0) -> list[dict[str, object]]:
    """A flood of gossip, which is what a real world mostly produces."""
    return [event("gossip", start + index) for index in range(count)]


def test_an_empty_store_has_nothing_to_say() -> None:
    store = EventStore()

    assert store.recent() == []
    assert store.recent(event_type="gossip") == []
    assert len(store) == 0


def test_the_feed_reads_newest_first() -> None:
    store = EventStore()
    store.extend([event("trade", 1), event("trade", 2), event("trade", 3)])

    assert [item["tick"] for item in store.recent()] == [3, 2, 1]


def test_the_chronological_feed_is_bounded() -> None:
    store = EventStore(chronological=10, per_type=5)

    store.extend(noise(50))

    assert len(store) == 10


def test_a_rare_event_survives_a_flood_of_gossip() -> None:
    """The actual bug: 500 gossip events buried the coup you were looking for."""
    store = EventStore(chronological=100, per_type=10)
    store.extend([event("coup", 1)])

    store.extend(noise(500, start=2))

    assert store.recent(event_type="coup"), "the coup should still be findable"
    assert store.recent(event_type="coup")[0]["tick"] == 1
    # And it is genuinely gone from the chronological view, which is why
    # filtering that view would have returned nothing.
    assert all(item["type"] == "gossip" for item in store.recent(limit=100))


def test_each_type_keeps_its_own_history() -> None:
    store = EventStore(chronological=1000, per_type=3)

    store.extend([event("coup", index) for index in range(10)])
    store.extend([event("birth", index) for index in range(10)])

    assert [item["tick"] for item in store.recent(event_type="coup")] == [9, 8, 7]
    assert [item["tick"] for item in store.recent(event_type="birth")] == [9, 8, 7]


def test_a_limit_is_honoured_in_both_views() -> None:
    store = EventStore()
    store.extend(noise(30))
    store.extend([event("gift", 100)])

    assert len(store.recent(limit=5)) == 5
    assert len(store.recent(limit=1, event_type="gossip")) == 1


def test_an_unknown_type_is_empty_not_an_error() -> None:
    store = EventStore()
    store.extend(noise(5))

    assert store.recent(event_type="nothing_like_this") == []


def test_clearing_forgets_both_views() -> None:
    store = EventStore()
    store.extend([event("coup", 1), *noise(20)])

    store.clear()

    assert store.recent() == []
    assert store.recent(event_type="coup") == []
    assert store.counts() == {}


def test_counts_report_what_is_retained() -> None:
    store = EventStore(per_type=4)
    store.extend(noise(10))
    store.extend([event("war_declared", 1)])

    assert store.counts() == {"gossip": 4, "war_declared": 1}


def test_retention_is_bounded_overall() -> None:
    """Per-type retention must not become an unbounded leak."""
    store = EventStore(chronological=50, per_type=5)

    for kind in range(30):
        store.extend([event(f"kind_{kind}", index) for index in range(20)])

    retained = sum(store.counts().values())
    assert retained == 30 * 5, retained
    assert len(store) == 50
