"""Owns the engine thread and the outbound broadcast loop.

Two threads meet here, and the split is deliberate:

* the **engine thread** ticks the world and pushes finished frames into a
  bounded queue - it never touches asyncio and never blocks on a client;
* the **asyncio pump** drains that queue at the broadcast rate and fans
  envelopes out to subscribers.

Control commands go the other way through the engine's command queue, and the
REST endpoints wait for their own command to be applied before reporting
state, so `POST /sim/step` returns the tick the step produced.
"""

import asyncio
import queue
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from app.ai.llm.broker import IntentionBroker
from app.ai.llm.gateway import LLMGateway, LLMStatus
from app.ai.skills.registry import SkillRegistry
from app.core.logging import get_logger
from app.core.settings import Settings
from app.core.world_config import STRATEGY_NAMES, WorldConfig
from app.services import envelopes
from app.services.engine_factory import EngineBundle, build_engine_bundle
from app.services.envelopes import Envelope
from app.services.god_tools import TOOLS, GodContext, Intervention, Outcome
from app.services.metrics_service import MetricsService
from app.services.serialisation import dump_world, load_world
from app.services.world_queries import WorldQueries
from app.sim.clock import SPEED_PRESETS
from app.sim.engine import (
    EngineStatus,
    Intervene,
    Pause,
    Reset,
    Restore,
    SetSpeed,
    Shutdown,
    Start,
    Step,
)
from app.sim.events import EventType, SimEvent
from app.sim.frames import WorldFrame, encode_resources
from app.sim.world import World, WorldBuilder

Subscriber = Callable[[Envelope], Awaitable[None]]

LOG = get_logger(__name__)

FRAME_QUEUE_SIZE = 2
"""Keep the newest frames only: a slow client must not delay the engine."""

EVENT_QUEUE_SIZE = 64
RECENT_EVENTS = 500
COMMAND_TIMEOUT_S = 5.0
"""Generous: a `Reset` has to generate a world before it can be applied."""

COMMAND_POLL_S = 0.004


@dataclass(frozen=True, slots=True)
class SimStateView:
    """What `GET /api/sim/state` reports."""

    status: EngineStatus
    tick: int
    speed: float
    seed: int
    day: int
    season: str
    time_of_day: float
    is_night: bool
    population: int
    ticks_per_second: float
    placeholder: bool = False


class SimulationService:
    """Single owner of the engine, its thread, and everything broadcast."""

    def __init__(
        self,
        settings: Settings,
        gateway: LLMGateway,
        bundle: EngineBundle | None = None,
        config: WorldConfig | None = None,
        metrics: MetricsService | None = None,
    ) -> None:
        self._settings = settings
        self._gateway = gateway
        self._bundle = bundle or build_engine_bundle(settings, config)
        self._engine = self._bundle.engine
        self._metrics = metrics
        self._last_sampled_tick = -1
        self._queries = WorldQueries(self._engine, self._bundle.minds, self._bundle.ledger)

        self._frames: queue.Queue[WorldFrame] = queue.Queue(maxsize=FRAME_QUEUE_SIZE)
        self._event_batches: queue.Queue[list[SimEvent]] = queue.Queue(maxsize=EVENT_QUEUE_SIZE)
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=RECENT_EVENTS)
        self._last_amounts: dict[int, float] = {}

        self._subscribers: set[Subscriber] = set()
        self._thread: threading.Thread | None = None
        self._pump_task: asyncio.Task[None] | None = None

        self._engine.install_callbacks(on_frame=self._on_frame, on_events=self._on_events)

    # ------------------------------------------------------------ properties

    @property
    def queries(self) -> WorldQueries:
        """Read-only views of the world for the REST API."""
        return self._queries

    @property
    def skills(self) -> SkillRegistry:
        """The skill registry the running pipeline uses."""
        return self._bundle.skills

    @property
    def broker(self) -> IntentionBroker:
        """The mailbox the LLM pump works from."""
        return self._bundle.broker

    @property
    def config(self) -> WorldConfig:
        """The config the current world was built from."""
        return self._engine.config

    @property
    def subscriber_count(self) -> int:
        """How many transports are currently attached."""
        return len(self._subscribers)

    # ------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        """Start the engine thread and the broadcast pump, then run."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._engine.run, name="sim-engine", daemon=True)
            self._thread.start()
        if self._pump_task is None or self._pump_task.done():
            self._pump_task = asyncio.create_task(self._pump(), name="sim-broadcast")

        await self._submit(Start())
        LOG.info(
            "simulation.started",
            seed=self.config.seed,
            population=self._engine.snapshot().population,
            resources=self._engine.snapshot().resources,
        )

    async def shutdown(self) -> None:
        """Stop the pump, then the engine thread."""
        task, self._pump_task = self._pump_task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            self._engine.submit(Shutdown())
            await asyncio.to_thread(thread.join, 3.0)
        LOG.info("simulation.stopped", tick=self._engine.snapshot().tick)

    # --------------------------------------------------------------- pub/sub

    def subscribe(self, subscriber: Subscriber) -> None:
        """Register an async callback that receives every envelope."""
        self._subscribers.add(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        """Remove a previously registered callback."""
        self._subscribers.discard(subscriber)

    async def broadcast(self, envelope: Envelope) -> None:
        """Send `envelope` to every subscriber, dropping ones that fail."""
        for subscriber in tuple(self._subscribers):
            try:
                await subscriber(envelope)
            # A failing subscriber must never stop the broadcast loop.
            except Exception as exc:
                LOG.warning("broadcast.subscriber_failed", error=str(exc))
                self._subscribers.discard(subscriber)

    # ----------------------------------------------------------------- state

    def state(self) -> SimStateView:
        """Return a snapshot of simulation state."""
        snapshot = self._engine.snapshot()
        return SimStateView(
            status=snapshot.status,
            tick=snapshot.tick,
            speed=snapshot.speed,
            seed=snapshot.seed,
            day=snapshot.day,
            season=snapshot.season,
            time_of_day=snapshot.time_of_day,
            is_night=snapshot.is_night,
            population=snapshot.population,
            ticks_per_second=snapshot.ticks_per_second,
        )

    def llm_status(self) -> LLMStatus:
        """Return LLM gateway status for the health endpoint."""
        return self._gateway.status()

    def recent_events(
        self, limit: int = 100, event_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Return the newest events, newest first, optionally filtered."""
        selected = [
            event
            for event in reversed(self._recent_events)
            if event_type is None or event["type"] == event_type
        ]
        return selected[:limit]

    def hello(self) -> Envelope:
        """Build the `hello` envelope: config, terrain meta, legends, resources."""
        snapshot = self._engine.snapshot()
        with self._engine.read_world() as world:
            resources = encode_resources(world)
            terrain = world.terrain
            terrain_meta = {
                "size": terrain.size,
                "resolution": terrain.resolution,
                "water_level": terrain.water_level,
                "max_height": world.config.terrain.max_height,
                "available": True,
            }
        return envelopes.hello(
            snapshot.tick,
            {
                "config": self.config.model_dump(mode="json"),
                "terrain": terrain_meta,
                "legend": {
                    "states": list(envelopes.AGENT_STATE_CODES),
                    "biomes": list(envelopes.BIOME_CODES),
                    "resources": list(envelopes.RESOURCE_CODES),
                },
                "resources": {"stride": envelopes.RESOURCE_STRIDE, "nodes": resources},
                "state": {
                    "status": snapshot.status.value,
                    "tick": snapshot.tick,
                    "speed": snapshot.speed,
                    "seed": snapshot.seed,
                    "day": snapshot.day,
                    "season": snapshot.season,
                    "time_of_day": round(snapshot.time_of_day, 4),
                    "population": snapshot.population,
                },
            },
        )

    # --------------------------------------------------------------- control

    async def play(self) -> SimStateView:
        """Resume ticking."""
        return await self._submit(Start())

    async def pause(self) -> SimStateView:
        """Stop ticking, keep the world."""
        return await self._submit(Pause())

    async def set_speed(self, multiplier: float) -> SimStateView:
        """Set the speed multiplier; `0` pauses and `-1` means MAX."""
        if multiplier not in SPEED_PRESETS:
            msg = f"speed must be one of {SPEED_PRESETS}, got {multiplier}"
            raise ValueError(msg)
        return await self._submit(SetSpeed(multiplier))

    async def step(self, n: int = 1) -> SimStateView:
        """Advance exactly `n` ticks and stay paused."""
        if n < 1:
            msg = "step count must be >= 1"
            raise ValueError(msg)
        return await self._submit(Step(n))

    async def reset(
        self,
        seed: int | None = None,
        config: WorldConfig | None = None,
    ) -> SimStateView:
        """Rebuild the world and stay paused at tick 0."""
        self._last_amounts.clear()
        self._recent_events.clear()
        self._last_sampled_tick = -1
        # Deliberations in flight belong to the world being thrown away. The
        # broker also stamps a world uid, so a reply that is already on its
        # way back is dropped rather than applied to the new world.
        self._bundle.broker.clear()
        if self._metrics is not None:
            self._metrics.clear()
        state = await self._submit(Reset(seed=seed, config=config))
        LOG.info("simulation.reset", seed=state.seed, population=state.population)
        return state

    async def intervene(self, action: str, request: Intervention) -> Outcome:
        """Run a god tool against the live world (SPEC 9.4).

        The tool itself runs on the engine thread, between ticks and under the
        engine's lock, because mutating a world mid-tick is how you get an
        agent halfway through an action it can no longer finish. This method
        waits for the acknowledgement, so the HTTP response describes what
        actually happened rather than what was requested.
        """
        tool = TOOLS.get(action)
        if tool is None:
            msg = f"unknown god action {action!r}"
            raise KeyError(msg)

        context = GodContext(minds=self._bundle.minds, strategies=STRATEGY_NAMES)
        done: list[Outcome] = []

        def apply(world: World) -> None:
            done.append(tool(world, request, context))

        sequence = self._engine.submit(Intervene(apply))
        deadline = time.monotonic() + COMMAND_TIMEOUT_S
        while self._engine.snapshot().commands_applied < sequence:
            if time.monotonic() >= deadline:
                LOG.warning("god.timeout", action=action)
                break
            await asyncio.sleep(0.005)

        outcome = done[0] if done else Outcome(detail="the engine did not apply it in time")
        LOG.info("god.applied", action=action, affected=outcome.affected, detail=outcome.detail)
        return outcome

    def capture(self) -> dict[str, Any]:
        """Serialise the live world, minds and ledger (SPEC 11).

        Reads under the engine lock, so the blob is one consistent instant
        rather than a mix of two ticks.
        """
        with self._engine.read_world() as world:
            return dump_world(world, self._bundle.minds, self._bundle.ledger)

    async def restore(self, payload: dict[str, Any]) -> SimStateView:
        """Replace the running world with a saved one.

        Rebuilt on the engine thread like a `Reset`, because swapping the
        world under a running tick would leave half the systems looking at
        the old one. The world arrives paused, as after any reset.
        """
        self._last_amounts.clear()
        self._recent_events.clear()
        self._last_sampled_tick = -1
        self._bundle.broker.clear()
        if self._metrics is not None:
            self._metrics.clear()

        def build(builder: WorldBuilder) -> World:
            return load_world(payload, builder, self._bundle.minds, self._bundle.ledger)

        sequence = self._engine.submit(Restore(build))
        await self._await_sequence(sequence)
        state = self.state()
        LOG.info("simulation.restored", tick=state.tick, population=state.population)
        return state

    async def _await_sequence(self, sequence: int) -> None:
        """Wait until the engine has applied the command with `sequence`."""
        deadline = time.monotonic() + COMMAND_TIMEOUT_S
        while self._engine.snapshot().commands_applied < sequence:
            if time.monotonic() >= deadline:
                LOG.warning("simulation.command_timeout", sequence=sequence)
                return
            await asyncio.sleep(COMMAND_POLL_S)

    async def _submit(self, command: Start | Pause | SetSpeed | Step | Reset) -> SimStateView:
        """Queue `command`, wait for it to take effect, return the new state."""
        sequence = self._engine.submit(command)
        deadline = time.monotonic() + COMMAND_TIMEOUT_S
        while self._engine.snapshot().commands_applied < sequence:
            if time.monotonic() >= deadline:
                LOG.warning("simulation.command_timeout", command=type(command).__name__)
                break
            await asyncio.sleep(COMMAND_POLL_S)
        return self.state()

    # ---------------------------------------------------- engine-thread hooks

    def _on_frame(self, frame: WorldFrame) -> None:
        """Engine thread: hand a frame to the pump, dropping the stale one.

        Dropping the old frame rather than the new one is the point: a client
        that falls behind should see the present, not a backlog of the past.
        """
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            with suppress(queue.Empty):
                self._frames.get_nowait()
            with suppress(queue.Full):
                self._frames.put_nowait(frame)

    def _on_events(self, batch: list[SimEvent]) -> None:
        """Engine thread: hand a batch of events to the pump."""
        try:
            self._event_batches.put_nowait(batch)
        except queue.Full:
            LOG.debug("events.dropped", count=len(batch))

    # ------------------------------------------------------------------- pump

    async def _pump(self) -> None:
        """Drain engine output and broadcast it at the configured rate."""
        interval = 1.0 / max(1.0, self._settings.sim_broadcast_hz)
        while True:
            await asyncio.sleep(interval)
            frame = self._latest_frame()
            if frame is not None:
                await self.broadcast(self._frame_envelope(frame))
                self._apply_speed_policy(frame.speed)
                await self._maybe_sample(frame.tick)
            await self._drain_events()

    def _apply_speed_policy(self, speed: float) -> None:
        """Tell the deliberative layer how often to think at this speed.

        Deliberation is the one part of the tick whose cost is not ours to
        control, so at high speed it thins out (`reduced`) or stops (`off`)
        rather than the world slowing to wait for a model. Pushed on every
        frame because the user can change both the speed and the policy
        while it runs.
        """
        limits = self._gateway.scheduler.limits
        interval = limits.interval_for_speed(speed) if self._gateway.enabled else None
        self._bundle.broker.set_interval(interval)

    async def _maybe_sample(self, tick: int) -> None:
        """Take a metrics sample if one is due, and broadcast it.

        Sampling happens here rather than inside the tick loop so the cost
        lands on the broadcast thread, never on the engine. That means the
        sampler only ever sees the ticks that happen to land on a frame, so
        "is one due" has to be a question about elapsed ticks (`is_due`) and
        not about divisibility: at 25x the frames are ~12 ticks apart and a
        test for `tick % 100 == 0` missed nearly every window, which left the
        charts panel with a single data point after six thousand ticks.
        """
        if self._metrics is None or not self._metrics.is_due(tick, self._last_sampled_tick):
            return

        with self._engine.read_world() as world:
            point = self._metrics.sample(world, self._bundle.ledger, self._bundle.minds)

        # Book the tick that was *recorded*, not the frame tick that triggered
        # this. The engine keeps running while the frame is in flight, so the
        # world is tens of ticks further on by the time we read it; charging
        # the interval to the frame tick made the recorded spacing drift below
        # the interval (a run showed 82 ticks between two "every 100" points).
        self._last_sampled_tick = point.tick

        await self.broadcast(
            envelopes.metrics(
                point.tick,
                {
                    "population": point.population,
                    "cooperation_rate": point.cooperation_rate,
                    "food_gini": point.food_gini,
                    "trust_density": point.trust_density,
                    "by_strategy": point.by_strategy,
                    "by_tribe": point.by_tribe,
                    "extra": point.extra,
                },
            )
        )

    def _latest_frame(self) -> WorldFrame | None:
        """Return the newest queued frame, discarding anything older."""
        newest: WorldFrame | None = None
        while True:
            try:
                newest = self._frames.get_nowait()
            except queue.Empty:
                return newest

    def _frame_envelope(self, frame: WorldFrame) -> Envelope:
        """Build a frame envelope, sending resource amounts as deltas."""
        changed: list[float] = []
        for node_id, fullness in frame.resource_fullness.items():
            if self._last_amounts.get(node_id) != fullness:
                changed.extend((float(node_id), fullness))
        gone = self._last_amounts.keys() - frame.resource_fullness.keys()
        removed = [float(node_id) for node_id in sorted(gone)]
        self._last_amounts = frame.resource_fullness

        return envelopes.frame(
            frame.tick,
            frame.agents,
            frame.time_of_day,
            status=frame.status,
            speed=frame.speed,
            day=frame.day,
            season=frame.season,
            population=frame.population,
            resources=changed,
            removed=removed,
        )

    async def _drain_events(self) -> None:
        """Broadcast and remember every queued event batch."""
        while True:
            try:
                batch = self._event_batches.get_nowait()
            except queue.Empty:
                return
            items = [self._event_dict(event) for event in batch]
            self._recent_events.extend(items)
            if items:
                await self.broadcast(envelopes.events(items[-1]["tick"], items))
            await self._broadcast_speech(batch)

    async def _broadcast_speech(self, batch: list[SimEvent]) -> None:
        """Send what was said as its own envelope, as well as an event.

        Speech is in the event feed because it is part of the story, and on
        its own channel because the scene needs it separately: a bubble has
        to appear over the right head and expire on its own timer, which the
        feed knows nothing about.
        """
        for event in batch:
            if event.type is not EventType.SPEECH:
                continue
            text = event.data.get("text")
            if not isinstance(text, str) or not text or not event.actors:
                continue
            await self.broadcast(envelopes.speech(event.tick, event.actors[0], text))

    @staticmethod
    def _event_dict(event: SimEvent) -> dict[str, Any]:
        """Return the wire form of one event."""
        return {
            "tick": event.tick,
            "type": event.type.value,
            "summary": event.summary,
            "importance": event.importance,
            "actors": list(event.actors),
            "x": None if event.position is None else round(event.position[0], 2),
            "z": None if event.position is None else round(event.position[1], 2),
        }
