"""Engine control: pause, play, speed presets, step and reset.

These drive the real worker thread, because the thing worth testing is the
command queue and the acknowledgement path, not a mock of them.
"""

import threading
from collections.abc import Iterator

import pytest

from app.ai.minds import MindRegistry
from app.ai.skills.registry import build_registry
from app.core.world_config import WorldConfig
from app.services.engine_factory import build_pipeline
from app.services.pacer import FrozenPacer, MonotonicPacer
from app.sim.clock import MAX_SPEED
from app.sim.engine import (
    MAX_DEBT_TICKS,
    MAX_TICKS_PER_SLICE,
    EngineStatus,
    Pause,
    Reset,
    SetSpeed,
    Shutdown,
    SimulationEngine,
    Start,
    Step,
)
from app.sim.frames import WorldFrame
from app.sim.worldgen import IslandWorldBuilder
from tests.conftest import SMALL_TERRAIN, wait_until


@pytest.fixture
def engine() -> Iterator[SimulationEngine]:
    """A running engine on its own thread, shut down at the end of the test."""
    config = WorldConfig(seed=3, population=12, max_agents=32, terrain=SMALL_TERRAIN)
    built = SimulationEngine(
        config=config,
        builder=IslandWorldBuilder(),
        pacer=MonotonicPacer(),
        pipeline=build_pipeline(MindRegistry(), build_registry(), temperature=0.35),
        frame_hz=50.0,
    )
    thread = threading.Thread(target=built.run, name="test-engine", daemon=True)
    thread.start()
    try:
        yield built
    finally:
        built.submit(Shutdown())
        thread.join(timeout=5.0)


def applied(engine: SimulationEngine, sequence: int) -> bool:
    """Whether the engine has applied the command with `sequence`."""
    return engine.snapshot().commands_applied >= sequence


def test_a_new_engine_starts_paused_at_tick_zero(engine: SimulationEngine) -> None:
    snapshot = engine.snapshot()

    assert snapshot.status is EngineStatus.PAUSED
    assert snapshot.tick == 0
    assert snapshot.population == 12
    assert snapshot.resources > 0


def test_start_makes_the_world_tick(engine: SimulationEngine) -> None:
    engine.submit(Start())

    assert wait_until(lambda: engine.snapshot().tick > 0)
    assert engine.snapshot().status is EngineStatus.RUNNING


def test_pause_freezes_the_tick(engine: SimulationEngine) -> None:
    engine.submit(Start())
    assert wait_until(lambda: engine.snapshot().tick > 0)

    sequence = engine.submit(Pause())
    assert wait_until(lambda: applied(engine, sequence))
    frozen = engine.snapshot().tick

    assert wait_until(lambda: False, timeout=0.2) is False
    assert engine.snapshot().tick == frozen
    assert engine.snapshot().status is EngineStatus.PAUSED


def test_step_advances_exactly_n_ticks(engine: SimulationEngine) -> None:
    sequence = engine.submit(Pause())
    assert wait_until(lambda: applied(engine, sequence))
    before = engine.snapshot().tick

    sequence = engine.submit(Step(7))
    # Waiting on the acknowledgement alone is not enough any more: a step
    # runs in time-budgeted chunks, so being accepted and being finished are
    # two different moments, and under load the first chunk ran four of the
    # seven ticks. Nor is waiting on `skip_remaining == 0` alone - it reads
    # zero before the engine has picked the command up at all. Both, then.
    assert wait_until(lambda: applied(engine, sequence) and engine.snapshot().skip_remaining == 0)

    assert engine.snapshot().tick == before + 7
    assert engine.snapshot().status is EngineStatus.PAUSED


def test_steps_accumulate(engine: SimulationEngine) -> None:
    engine.submit(Pause())
    before = engine.snapshot().tick
    engine.submit(Step(3))
    sequence = engine.submit(Step(4))

    assert wait_until(lambda: engine.snapshot().tick >= before + 7)
    assert applied(engine, sequence)
    assert engine.snapshot().tick == before + 7


def test_a_long_skip_runs_in_chunks_and_can_be_cancelled(
    engine: SimulationEngine,
) -> None:
    """A skip bigger than a batch must not hold the world hostage.

    A day is 2,400 ticks. Run in one slice that is a lock held for tens of
    seconds: no frames, no commands read, and a websocket that gives up
    after six - a UI that looks crashed. So the engine owes the ticks, says
    how many are left, and Pause is still heard while it works.
    """
    engine.submit(Pause())
    assert wait_until(lambda: engine.snapshot().skip_remaining == 0)
    before = engine.snapshot().tick

    engine.submit(Step(100_000))
    assert wait_until(lambda: engine.snapshot().skip_remaining > 0)
    assert wait_until(lambda: engine.snapshot().tick > before), "it should be ticking"

    sequence = engine.submit(Pause())
    assert wait_until(lambda: applied(engine, sequence)), "Pause is heard mid-skip"
    assert engine.snapshot().skip_remaining == 0, "and abandons what it owed"

    settled = engine.snapshot().tick
    assert wait_until(lambda: engine.snapshot().tick == settled)
    assert engine.snapshot().tick < before + 100_000


def test_speed_zero_pauses(engine: SimulationEngine) -> None:
    engine.submit(Start())
    sequence = engine.submit(SetSpeed(0.0))

    assert wait_until(lambda: applied(engine, sequence))
    assert engine.snapshot().status is EngineStatus.PAUSED


def test_a_higher_speed_ticks_faster(engine: SimulationEngine) -> None:
    engine.submit(SetSpeed(1.0))
    engine.submit(Start())
    assert wait_until(lambda: engine.snapshot().tick > 2)
    slow_start = engine.snapshot().tick
    assert wait_until(lambda: engine.snapshot().tick >= slow_start + 4, timeout=2.0)
    slow_ticks = engine.snapshot().tick - slow_start

    engine.submit(SetSpeed(25.0))
    assert wait_until(lambda: engine.snapshot().speed == 25.0)
    fast_start = engine.snapshot().tick
    assert wait_until(lambda: engine.snapshot().tick >= fast_start + 4, timeout=2.0)

    assert engine.snapshot().speed == 25.0
    assert slow_ticks > 0


def test_max_speed_runs_without_pacing(engine: SimulationEngine) -> None:
    engine.submit(SetSpeed(MAX_SPEED))
    engine.submit(Start())

    assert wait_until(lambda: engine.snapshot().tick > 200, timeout=5.0)
    assert engine.snapshot().speed == MAX_SPEED


def test_reset_rebuilds_the_world_at_tick_zero(engine: SimulationEngine) -> None:
    engine.submit(Start())
    assert wait_until(lambda: engine.snapshot().tick > 3)

    sequence = engine.submit(Reset(seed=777))
    assert wait_until(lambda: applied(engine, sequence))

    snapshot = engine.snapshot()
    assert snapshot.tick == 0
    assert snapshot.seed == 777
    assert snapshot.status is EngineStatus.PAUSED
    assert snapshot.population == 12


def test_reset_can_change_the_config(engine: SimulationEngine) -> None:
    config = WorldConfig(seed=4, population=5, max_agents=8, terrain=SMALL_TERRAIN)

    sequence = engine.submit(Reset(config=config))
    assert wait_until(lambda: applied(engine, sequence))

    assert engine.snapshot().population == 5
    assert engine.config.population == 5


def test_frames_are_emitted_while_running(engine: SimulationEngine) -> None:
    received: list[WorldFrame] = []
    engine.install_callbacks(on_frame=received.append)
    engine.submit(Start())

    assert wait_until(lambda: len(received) >= 3)
    frame = received[-1]
    assert frame.agents, "a frame must carry agents"
    assert len(frame.agents) % 7 == 0
    assert frame.status == "running"


def test_read_world_sees_a_consistent_world(engine: SimulationEngine) -> None:
    engine.submit(Start())
    assert wait_until(lambda: engine.snapshot().tick > 2)

    with engine.read_world() as world:
        assert world.population == len(world.living_agents())
        assert len(world.agent_index) == world.population


def test_shutdown_stops_a_busy_engine_promptly(engine: SimulationEngine) -> None:
    """A world running flat out must still stop when asked.

    This is the dev-loop test: uvicorn --reload terminates the worker and
    waits for it to exit, so an engine that keeps spinning after Shutdown
    wedges the backend on every code edit until the machine is rebooted.
    """
    engine.submit(SetSpeed(MAX_SPEED))
    sequence = engine.submit(Start())
    assert wait_until(lambda: applied(engine, sequence)), "engine never started"
    assert wait_until(lambda: engine.snapshot().tick > 50), "engine never got busy"

    engine.submit(Shutdown())

    assert wait_until(lambda: engine.snapshot().status is EngineStatus.STOPPED, timeout=3.0), (
        "the engine ignored Shutdown while running at MAX speed"
    )


# ------------------------------------------------------------------ pacing


def paced_engine(pacer: FrozenPacer) -> SimulationEngine:
    """An engine on a fake clock, not started - the pacing maths only."""
    config = WorldConfig(seed=4, population=6, max_agents=16, terrain=SMALL_TERRAIN)
    return SimulationEngine(
        config=config,
        builder=IslandWorldBuilder(),
        pacer=pacer,
        pipeline=build_pipeline(MindRegistry(), build_registry(), temperature=0.35),
        frame_hz=50.0,
    )


def ticks_for(speed: float, elapsed: float) -> int:
    """How many ticks `elapsed` real seconds earn at `speed`.

    Driven through `_run_slice` directly rather than the thread: the question
    is the arithmetic, and a real clock makes it unanswerable. This is what
    `FrozenPacer` exists for - it was an unused seam until this test.
    """
    pacer = FrozenPacer()
    engine = paced_engine(pacer)
    engine.submit(SetSpeed(speed))
    engine._drain_commands()
    before = engine.snapshot().tick
    engine._run_slice(elapsed, pacer.monotonic())
    engine._publish()
    return engine.snapshot().tick - before


def test_one_real_second_at_1x_is_the_tick_rate() -> None:
    """Dt is 0.1 sim-seconds, so 1x earns ten ticks a second."""
    assert ticks_for(1.0, 1.0) == 10


def test_speed_multiplies_the_ticks_earned() -> None:
    assert ticks_for(2.0, 1.0) == 20
    assert ticks_for(5.0, 1.0) == 50
    assert ticks_for(10.0, 0.5) == 50


def test_fractional_ticks_are_banked_rather_than_lost() -> None:
    """At 20 Hz each slice earns half a tick at 1x; they must accumulate."""
    pacer = FrozenPacer()
    engine = paced_engine(pacer)
    engine.submit(SetSpeed(1.0))
    engine._drain_commands()

    engine._run_slice(0.05, pacer.monotonic())
    engine._publish()
    assert engine.snapshot().tick == 0, "half a tick is not a tick"

    engine._run_slice(0.05, pacer.monotonic())
    engine._publish()
    assert engine.snapshot().tick == 1, "two halves are"


def test_a_long_stall_cannot_run_an_unbounded_batch() -> None:
    """A debugger pause must not then freeze the world catching up.

    This used to assert only `<= MAX_TICKS_PER_SLICE`, which is 4,096 - a
    bound so loose it passed while the real bug was live. At 25x with 400
    agents a 4,096-tick batch takes over a minute, and it holds the world
    lock the whole time, so the backend looks dead. The debt ceiling is the
    bound that means something.
    """
    pacer = FrozenPacer()
    engine = paced_engine(pacer)
    engine.submit(SetSpeed(10.0))
    engine._drain_commands()

    engine._run_slice(60.0, pacer.monotonic())
    engine._publish()

    ticks = engine.snapshot().tick
    assert 0 < ticks <= MAX_DEBT_TICKS
    assert MAX_DEBT_TICKS < MAX_TICKS_PER_SLICE, "the count cap is the backstop, not the bound"


def test_a_slice_stops_when_its_time_is_up_even_with_debt_owing() -> None:
    """The bound that actually keeps the world answering.

    A tick-count cap is not a limit on time: how long 4,096 ticks take
    depends on the population, and at 400 agents it is over a minute of held
    lock. MAX speed always had a wall-clock budget; every other speed had
    only the count, which is how 25x came to freeze the backend outright.

    Here each tick costs a millisecond of fake time, so a 12 ms budget must
    buy about a dozen ticks and then stop, with the rest of the debt left
    for the next slice.
    """
    pacer = FrozenPacer()
    engine = paced_engine(pacer)
    engine.submit(SetSpeed(50.0))
    engine._drain_commands()

    real_tick = engine._tick

    def slow_tick() -> None:
        pacer.now += 0.001  # a millisecond a tick
        real_tick()

    engine._tick = slow_tick  # type: ignore[method-assign]
    engine._run_slice(10.0, pacer.monotonic())
    engine._publish()

    ticks = engine.snapshot().tick
    assert 1 <= ticks <= 20, f"a 12 ms budget at 1 ms a tick ran {ticks} ticks"
    assert engine._tick_debt > 0, "the unpaid debt stays owing rather than vanishing"


def test_negative_elapsed_time_earns_nothing() -> None:
    """A clock that goes backwards must not rewind or explode the debt."""
    assert ticks_for(1.0, -5.0) == 0


def test_the_loop_only_yields_briefly_when_it_is_behind(engine: SimulationEngine) -> None:
    """The policy that made MAX three times faster, stated directly.

    The loop used to sleep 20 ms after every batch at every speed, so a
    12 ms batch was followed by 20 ms of nothing and MAX delivered a third
    of what the machine could do. It now sleeps 2 ms instead whenever the
    user has asked for ticks faster than they are arriving - and only
    then, because a speed the engine is keeping up with should leave the
    core alone.
    """
    engine.submit(Pause())
    assert wait_until(lambda: engine.snapshot().status is EngineStatus.PAUSED)
    assert not engine._is_busy(), "a paused world is not in a hurry"

    engine.submit(SetSpeed(1.0))
    assert wait_until(lambda: engine.snapshot().speed == 1.0)
    assert not engine._is_busy(), "a speed it keeps up with paces itself"

    engine.submit(SetSpeed(MAX_SPEED))
    assert wait_until(lambda: engine.snapshot().speed == MAX_SPEED)
    assert engine._is_busy(), "MAX means as fast as the machine allows"

    engine.submit(Pause())
    assert wait_until(lambda: engine.snapshot().status is EngineStatus.PAUSED)
    engine.submit(Step(50_000))
    assert wait_until(lambda: engine.snapshot().skip_remaining > 0)
    assert engine._is_busy(), "a skip is a request to get there quickly"
    engine.submit(Pause())
