"""The broadcast pump, tested without an engine.

Being able to write this file is the point of extracting it: these behaviours
- dropping the stale frame, sending resource amounts as deltas, surviving a
subscriber that throws - were previously reachable only through the HTTP API
and a running simulation.
"""

import asyncio

import pytest

from app.services.broadcast import BroadcastPump, event_dict
from app.services.envelopes import Envelope, MessageType
from app.sim.events import EventType, SimEvent
from app.sim.frames import WorldFrame


def frame(tick: int, **extra: object) -> WorldFrame:
    """A minimal broadcastable frame."""
    defaults: dict[str, object] = {
        "agents": [0.0, 1.0, 2.0, 0.0, 0.0, -1.0, 0.0],
        "time_of_day": 0.5,
        "day": 1,
        "season": "spring",
        "population": 1,
        "status": "running",
        "speed": 1.0,
        "resource_fullness": {},
    }
    defaults.update(extra)
    return WorldFrame(tick=tick, **defaults)  # type: ignore[arg-type]


def sim_event(kind: EventType = EventType.TRADE, tick: int = 1, **extra: object) -> SimEvent:
    """One simulation event."""
    return SimEvent(
        tick=tick,
        type=kind,
        summary=f"{kind.value} happened",
        importance=5,
        **extra,  # type: ignore[arg-type]
    )


class Recorder:
    """A subscriber that keeps what it was sent."""

    def __init__(self) -> None:
        self.envelopes: list[Envelope] = []

    async def __call__(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)

    def of_type(self, kind: str) -> list[Envelope]:
        return [envelope for envelope in self.envelopes if envelope.type == kind]


# --------------------------------------------------------------- queueing


def test_a_full_frame_queue_drops_the_stale_frame() -> None:
    """A client that falls behind should see the present, not the past."""
    pump = BroadcastPump(broadcast_hz=20.0)

    for tick in range(10):
        pump.accept_frame(frame(tick))

    newest = pump._latest_frame()  # the queue is the unit under test
    assert newest is not None
    assert newest.tick == 9, "the newest frame should have survived"


def test_draining_an_empty_queue_is_not_an_error() -> None:
    assert BroadcastPump(broadcast_hz=20.0)._latest_frame() is None


def test_accepting_events_never_blocks_the_engine() -> None:
    """The engine thread must never wait on a slow consumer."""
    pump = BroadcastPump(broadcast_hz=20.0)

    for tick in range(500):
        pump.accept_events([sim_event(tick=tick)])

    # No exception, no hang: excess batches are dropped with a log line.
    assert True


# ----------------------------------------------------------------- pub/sub


async def test_every_subscriber_receives_every_envelope() -> None:
    pump = BroadcastPump(broadcast_hz=20.0)
    first, second = Recorder(), Recorder()
    pump.subscribe(first)
    pump.subscribe(second)

    await pump.broadcast(Envelope(type=MessageType.HELLO, tick=0, data={}))

    assert len(first.envelopes) == 1
    assert len(second.envelopes) == 1
    assert pump.subscriber_count == 2


async def test_a_subscriber_that_throws_is_dropped_not_fatal() -> None:
    """One broken transport must not stop the world being broadcast."""
    pump = BroadcastPump(broadcast_hz=20.0)
    good = Recorder()

    async def broken(envelope: Envelope) -> None:
        msg = "this socket is gone"
        raise RuntimeError(msg)

    pump.subscribe(broken)
    pump.subscribe(good)

    await pump.broadcast(Envelope(type=MessageType.FRAME, tick=1, data={}))
    await pump.broadcast(Envelope(type=MessageType.FRAME, tick=2, data={}))

    assert len(good.envelopes) == 2, "the healthy subscriber kept receiving"
    assert pump.subscriber_count == 1, "the broken one was dropped"


async def test_unsubscribing_stops_the_envelopes() -> None:
    pump = BroadcastPump(broadcast_hz=20.0)
    recorder = Recorder()
    pump.subscribe(recorder)
    pump.unsubscribe(recorder)

    await pump.broadcast(Envelope(type=MessageType.FRAME, tick=1, data={}))

    assert recorder.envelopes == []


# ------------------------------------------------------------ frame deltas


def test_resource_amounts_are_sent_as_deltas() -> None:
    """Sending every node every frame would be most of the payload."""
    pump = BroadcastPump(broadcast_hz=20.0)

    first = pump._frame_envelope(frame(1, resource_fullness={1: 1.0, 2: 0.5}))
    assert sorted(first.data["resources"]) == [0.5, 1.0, 1.0, 2.0]

    # Nothing changed, so nothing is sent.
    unchanged = pump._frame_envelope(frame(2, resource_fullness={1: 1.0, 2: 0.5}))
    assert unchanged.data["resources"] == []

    # One node emptied: only that one travels.
    changed = pump._frame_envelope(frame(3, resource_fullness={1: 1.0, 2: 0.0}))
    assert changed.data["resources"] == [2.0, 0.0]


def test_a_vanished_node_is_reported_as_removed() -> None:
    """A rotted corpse has to disappear from the scene, not linger."""
    pump = BroadcastPump(broadcast_hz=20.0)
    pump._frame_envelope(frame(1, resource_fullness={7: 1.0, 8: 1.0}))

    envelope = pump._frame_envelope(frame(2, resource_fullness={7: 1.0}))

    assert envelope.data["removed"] == [8.0]


def test_clearing_forgets_the_deltas() -> None:
    """After a reset every amount is new again, or the scene shows stale nodes."""
    pump = BroadcastPump(broadcast_hz=20.0)
    pump._frame_envelope(frame(1, resource_fullness={1: 1.0}))

    pump.clear()
    envelope = pump._frame_envelope(frame(1, resource_fullness={1: 1.0}))

    assert envelope.data["resources"] == [1.0, 1.0]


# ------------------------------------------------------------------- loop


async def test_the_loop_broadcasts_frames_and_events() -> None:
    pump = BroadcastPump(broadcast_hz=200.0)
    recorder = Recorder()
    pump.subscribe(recorder)
    pump.accept_frame(frame(5))
    pump.accept_events([sim_event(tick=5)])

    pump.start()
    for _ in range(50):
        await asyncio.sleep(0.01)
        if recorder.of_type("frame") and recorder.of_type("events"):
            break
    await pump.stop()

    assert recorder.of_type("frame"), "no frame was broadcast"
    assert recorder.of_type("events"), "no events were broadcast"
    assert pump.running is False


async def test_the_frame_hook_runs_once_per_frame() -> None:
    """Metrics sampling and the speed policy hang off this."""
    seen: list[int] = []

    async def hook(sent: WorldFrame) -> None:
        seen.append(sent.tick)

    pump = BroadcastPump(broadcast_hz=200.0, on_frame=hook)
    pump.accept_frame(frame(11))

    pump.start()
    for _ in range(50):
        await asyncio.sleep(0.01)
        if seen:
            break
    await pump.stop()

    assert seen == [11]


async def test_speech_gets_its_own_envelope_as_well_as_an_event() -> None:
    """A bubble expires on its own timer, which the feed knows nothing about."""
    pump = BroadcastPump(broadcast_hz=200.0)
    recorder = Recorder()
    pump.subscribe(recorder)
    pump.accept_events(
        [sim_event(EventType.SPEECH, tick=3, actors=(4,), data={"text": "A friend is cheaper"})]
    )

    pump.start()
    for _ in range(50):
        await asyncio.sleep(0.01)
        if recorder.of_type("speech"):
            break
    await pump.stop()

    speech = recorder.of_type("speech")
    assert speech, "speech should travel on its own channel"
    assert speech[0].data["agent"] == 4
    assert recorder.of_type("events"), "and still appear in the feed"


async def test_speech_with_no_text_or_no_speaker_is_ignored() -> None:
    pump = BroadcastPump(broadcast_hz=200.0)
    recorder = Recorder()
    pump.subscribe(recorder)
    pump.accept_events(
        [
            sim_event(EventType.SPEECH, tick=1, actors=(), data={"text": "nobody said this"}),
            sim_event(EventType.SPEECH, tick=2, actors=(1,), data={}),
        ]
    )

    pump.start()
    await asyncio.sleep(0.05)
    await pump.stop()

    assert recorder.of_type("speech") == []


async def test_stopping_a_pump_that_never_started_is_harmless() -> None:
    pump = BroadcastPump(broadcast_hz=20.0)

    await pump.stop()

    assert pump.running is False


# ------------------------------------------------------------- the feed


def test_the_feed_keeps_what_was_broadcast() -> None:
    pump = BroadcastPump(broadcast_hz=20.0)
    pump._store.extend([event_dict(sim_event(EventType.COUP, tick=1))])

    assert pump.recent_events(event_type="coup")
    assert pump.recent_events()[0]["type"] == "coup"


def test_the_wire_form_rounds_positions() -> None:
    event = sim_event(EventType.BIRTH, tick=2, position=(1.23456, -7.89123))

    wire = event_dict(event)

    assert wire == {
        "tick": 2,
        "type": "birth",
        "summary": "birth happened",
        "importance": 5,
        "actors": [],
        "x": 1.23,
        "z": -7.89,
    }


def test_an_event_without_a_position_says_so() -> None:
    wire = event_dict(sim_event(EventType.TRADE))

    assert wire["x"] is None
    assert wire["z"] is None


@pytest.mark.parametrize("hz", [0.0, -5.0, 1.0, 60.0])
def test_any_broadcast_rate_produces_a_sane_interval(hz: float) -> None:
    """A zero or negative rate must not divide by zero or busy-loop."""
    pump = BroadcastPump(broadcast_hz=hz)

    assert 0.0 < pump._interval <= 1.0
