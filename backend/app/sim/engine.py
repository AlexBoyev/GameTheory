"""The simulation engine: a worker-thread loop driven by a command queue.

Everything outside the engine thread interacts through `submit()` (commands
in), `snapshot()` (cheap state out) and `read_world()` (locked reads for the
API). Frames and events leave through callbacks installed by the service.

The loop is deliberately boring: a tick is `pipeline.step(world, dt)` plus a
clock advance, and nothing in it reads the wall clock. Real time only decides
*how many* ticks to run, never what a tick does - which is what makes the
determinism test possible.
"""

import queue
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.core.world_config import Season, WorldConfig
from app.sim.clock import MAX_SPEED, SimClock, season_offset_for
from app.sim.events import SimEvent
from app.sim.frames import WorldFrame, encode_frame
from app.sim.systems import SystemPipeline
from app.sim.world import World, WorldBuilder

CONTROL_SLICE_S = 0.02
"""How often the loop wakes to look at commands - a 50 Hz control rate."""

MAX_BATCH_BUDGET_S = 0.012
"""At MAX speed, how long one batch of ticks may run before yielding."""

MAX_TICKS_PER_SLICE = 4096
"""Hard cap so a huge speed multiplier cannot starve the command queue."""

TPS_WINDOW_S = 1.0


class EngineStatus(StrEnum):
    """Lifecycle state reported to the UI."""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class Start:
    """Resume ticking."""


@dataclass(frozen=True, slots=True)
class Pause:
    """Stop ticking but keep the world."""


@dataclass(frozen=True, slots=True)
class SetSpeed:
    """Change the speed multiplier; `-1.0` means MAX."""

    multiplier: float


@dataclass(frozen=True, slots=True)
class Step:
    """Advance exactly `n` ticks while paused."""

    n: int = 1


@dataclass(frozen=True, slots=True)
class Reset:
    """Rebuild the world from `config` (and optionally a new `seed`)."""

    seed: int | None = None
    config: WorldConfig | None = None


@dataclass(frozen=True, slots=True)
class Shutdown:
    """Terminate the worker thread."""


type EngineCommand = Start | Pause | SetSpeed | Step | Reset | Shutdown


@dataclass(frozen=True, slots=True)
class EngineSnapshot:
    """Cheap, thread-safe view of engine state for `GET /api/sim/state`."""

    status: EngineStatus
    tick: int
    speed: float
    seed: int
    day: int
    season: Season
    time_of_day: float
    is_night: bool
    population: int
    ticks_per_second: float
    births: int
    deaths: int
    resources: int
    commands_applied: int
    """Lets a caller wait for its own command to have taken effect.

    Published at the end of a slice, after any ticks that command caused, so
    "my step has been applied" also means "its ticks are visible".
    """


class Pacer(Protocol):
    """Wall-clock access, injected so `sim/` stays free of real time."""

    def monotonic(self) -> float:
        """Seconds from an arbitrary monotonic origin."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block the calling thread for `seconds`."""
        ...


class SimulationEngine:
    """Owns the `World` and advances it on a dedicated thread."""

    def __init__(
        self,
        config: WorldConfig,
        builder: WorldBuilder,
        pacer: Pacer,
        pipeline: SystemPipeline | None = None,
        on_frame: Callable[[WorldFrame], None] | None = None,
        on_events: Callable[[list[SimEvent]], None] | None = None,
        frame_hz: float = 20.0,
    ) -> None:
        self._config = config
        self._builder = builder
        self._pacer = pacer
        self._pipeline = pipeline or SystemPipeline()
        self._on_frame = on_frame
        self._on_events = on_events
        self._frame_interval = 1.0 / max(1.0, frame_hz)

        self._commands: queue.Queue[EngineCommand] = queue.Queue()
        self._lock = threading.RLock()
        self._status = EngineStatus.PAUSED
        self._speed = 1.0
        self._tick_debt = 0.0
        self._step_remaining = 0
        self._shutdown = False
        self._pending_events: list[SimEvent] = []
        self._next_sequence = 0
        self._commands_applied = 0

        self._ticks_in_window = 0
        self._window_started = 0.0
        self._measured_tps = 0.0
        self._last_frame_at = 0.0

        self._world = builder.build(config)
        self._pipeline.on_world_replaced(self._world)
        self._snapshot = self._build_snapshot()

    # ------------------------------------------------------------ thread-safe

    @property
    def config(self) -> WorldConfig:
        """The config the current world was built from."""
        return self._config

    def install_callbacks(
        self,
        on_frame: Callable[[WorldFrame], None] | None = None,
        on_events: Callable[[list[SimEvent]], None] | None = None,
    ) -> None:
        """Attach output callbacks after construction.

        The service is built after the engine (it needs the engine to exist),
        so it installs its queue writers here rather than in the constructor.
        Call before `run()`.
        """
        if on_frame is not None:
            self._on_frame = on_frame
        if on_events is not None:
            self._on_events = on_events

    def submit(self, command: EngineCommand) -> int:
        """Queue `command` and return the sequence number to wait for.

        Callers that need to report the resulting state (every REST control
        endpoint) wait until `snapshot().commands_applied` reaches it.
        """
        self._next_sequence += 1
        self._commands.put(command)
        return self._next_sequence

    def snapshot(self) -> EngineSnapshot:
        """Return the most recently published engine state."""
        return self._snapshot

    @contextmanager
    def read_world(self) -> Iterator[World]:
        """Hold the engine lock and read the world.

        Keep the body short: the tick loop is waiting on this lock, and a slow
        reader shows up directly as a stuttering simulation.
        """
        with self._lock:
            yield self._world

    # ------------------------------------------------------------------ loop

    def run(self) -> None:
        """Run the tick loop until a `Shutdown` command arrives."""
        self._window_started = self._pacer.monotonic()
        last_slice = self._window_started

        while True:
            self._drain_commands()
            if self._shutdown:
                break

            now = self._pacer.monotonic()
            if self._step_remaining > 0:
                self._run_steps()
            elif self._status is EngineStatus.RUNNING:
                self._run_slice(now - last_slice, now)
            else:
                self._tick_debt = 0.0

            last_slice = now
            self._update_tps(now)
            # Republish every slice, not just on commands: `GET /sim/state`
            # should never be a second behind the world.
            self._publish()
            self._maybe_emit(now)
            self._pacer.sleep(CONTROL_SLICE_S)

        self._status = EngineStatus.STOPPED
        self._publish()

    def _run_steps(self) -> None:
        """Run the ticks a `Step` command asked for, then stay paused."""
        count = min(self._step_remaining, MAX_TICKS_PER_SLICE)
        self._step_remaining -= count
        with self._lock:
            for _ in range(count):
                self._tick()

    def _run_slice(self, elapsed: float, now: float) -> None:
        """Run the ticks that `elapsed` real seconds have earned."""
        if self._speed == MAX_SPEED:
            deadline = now + MAX_BATCH_BUDGET_S
            with self._lock:
                ticks = 0
                while self._pacer.monotonic() < deadline and ticks < MAX_TICKS_PER_SLICE:
                    self._tick()
                    ticks += 1
            return

        ticks_per_sim_second = 1.0 / self._config.dt
        self._tick_debt += max(0.0, elapsed) * ticks_per_sim_second * self._speed
        count = min(int(self._tick_debt), MAX_TICKS_PER_SLICE)
        if count <= 0:
            return
        self._tick_debt -= count
        with self._lock:
            for _ in range(count):
                self._tick()

    def _tick(self) -> None:
        """Advance the world exactly one fixed timestep. Caller holds the lock."""
        world = self._world
        self._pipeline.step(world, world.clock.dt)
        world.clock = world.clock.advance()
        self._ticks_in_window += 1
        if len(world.events) > 0:
            self._pending_events.extend(world.events.drain())

    # -------------------------------------------------------------- commands

    def _drain_commands(self) -> None:
        """Apply every queued command."""
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            self._apply(command)

    def _apply(self, command: EngineCommand) -> None:
        """Apply one command."""
        match command:
            case Start():
                self._status = EngineStatus.RUNNING
                self._tick_debt = 0.0
            case Pause():
                self._status = EngineStatus.PAUSED
                self._step_remaining = 0
            case SetSpeed(multiplier):
                if multiplier == 0.0:
                    self._status = EngineStatus.PAUSED
                else:
                    self._speed = multiplier
                    self._status = EngineStatus.RUNNING
                self._tick_debt = 0.0
            case Step(n):
                self._status = EngineStatus.PAUSED
                self._step_remaining += max(1, n)
            case Reset(seed, config):
                self._rebuild(seed, config)
            case Shutdown():
                self._shutdown = True
        self._commands_applied += 1

    def _rebuild(self, seed: int | None, config: WorldConfig | None) -> None:
        """Build a new world, leaving it paused at tick 0."""
        base = config or self._config
        self._config = base.model_copy(update={"seed": seed} if seed is not None else {})

        # Generate outside the lock: world generation takes most of a second,
        # and readers (the API) must not block on it.
        world = self._builder.build(self._config)
        world.clock = SimClock(
            dt=self._config.dt,
            day_seconds=self._config.day_seconds,
            days_per_season=self._config.days_per_season,
            season_offset=season_offset_for(self._config.season_start),
        )
        with self._lock:
            self._world = world
            self._pipeline.on_world_replaced(world)
        self._status = EngineStatus.PAUSED
        self._step_remaining = 0
        self._tick_debt = 0.0
        self._pending_events.clear()
        self._last_frame_at = 0.0

    # ---------------------------------------------------------------- output

    def _maybe_emit(self, now: float) -> None:
        """Emit a frame (and any batched events) at the broadcast rate."""
        if now - self._last_frame_at < self._frame_interval:
            return
        self._last_frame_at = now

        if self._on_frame is not None:
            with self._lock:
                frame = encode_frame(self._world, self._status.value, self._speed)
            self._on_frame(frame)

        if self._pending_events and self._on_events is not None:
            batch, self._pending_events = self._pending_events, []
            self._on_events(batch)

    def _update_tps(self, now: float) -> None:
        """Recompute the measured tick rate once per window."""
        if now - self._window_started < TPS_WINDOW_S:
            return
        span = now - self._window_started
        self._measured_tps = self._ticks_in_window / span if span > 0 else 0.0
        self._ticks_in_window = 0
        self._window_started = now
        self._publish()

    def _publish(self) -> None:
        """Republish the state snapshot readers see."""
        self._snapshot = self._build_snapshot()

    def _build_snapshot(self) -> EngineSnapshot:
        world = self._world
        return EngineSnapshot(
            status=self._status,
            tick=world.clock.tick,
            speed=self._speed,
            seed=self._config.seed,
            day=world.clock.day,
            season=world.clock.season,
            time_of_day=world.clock.time_of_day,
            is_night=world.clock.is_night,
            population=world.population,
            ticks_per_second=round(self._measured_tps, 1),
            births=world.births,
            deaths=world.deaths,
            resources=len(world.resources),
            commands_applied=self._commands_applied,
        )
