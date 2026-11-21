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
from app.services.pacer import MonotonicPacer
from app.sim.clock import MAX_SPEED
from app.sim.engine import (
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
    assert wait_until(lambda: applied(engine, sequence))

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
