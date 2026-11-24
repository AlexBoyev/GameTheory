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
import threading
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.ai.llm.broker import IntentionBroker
from app.ai.llm.gateway import LLMGateway, LLMStatus
from app.ai.skills.registry import SkillRegistry
from app.core.logging import get_logger
from app.core.settings import Settings
from app.core.world_config import STRATEGY_NAMES, WorldConfig
from app.services import envelopes
from app.services.broadcast import BroadcastPump, Subscriber
from app.services.engine_factory import EngineBundle, build_engine_bundle
from app.services.envelopes import Envelope
from app.services.god_tools import TOOLS, GodContext, Intervention, Outcome
from app.services.metrics_service import MetricsService
from app.services.run_archive import RunArchive
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
from app.sim.frames import WorldFrame, encode_resources
from app.sim.world import World, WorldBuilder

LOG = get_logger(__name__)


COMMAND_TIMEOUT_S = 5.0
"""Generous: a `Reset` has to generate a world before it can be applied."""

COMMAND_POLL_S = 0.004


@dataclass(frozen=True, slots=True)
class TournamentReport:
    """What `GET /api/sim/tournament` reports (SPEC 5.3)."""

    active: bool
    generation: int
    generations: int
    finished: bool
    pairings_played: int
    pairings_total: int
    standings: list[tuple[str, float, int]]
    """`(strategy, score per round, members)`, best first."""


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
        archive: RunArchive | None = None,
    ) -> None:
        self._settings = settings
        self._gateway = gateway
        self._bundle = bundle or build_engine_bundle(settings, config)
        self._engine = self._bundle.engine
        self._metrics = metrics
        self._archive = archive
        self._last_sampled_tick = -1
        self._queries = WorldQueries(self._engine, self._bundle.minds, self._bundle.ledger)

        self._pump = BroadcastPump(
            settings.sim_broadcast_hz,
            on_frame=self._on_frame,
            on_events=None if archive is None else archive.record_events,
        )
        self._thread: threading.Thread | None = None

        self._engine.install_callbacks(
            on_frame=self._pump.accept_frame, on_events=self._pump.accept_events
        )

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
        return self._pump.subscriber_count

    # ------------------------------------------------------------- lifecycle

    async def boot(self) -> None:
        """Bring the engine thread and the broadcast up, world still paused.

        Separate from `start` because a world that is *ready* and a world
        that is *running* are different things, and the app used to conflate
        them: the engine began ticking the moment the process did, so by the
        time the front screen had loaded and pressed pause the island was
        already a few hundred ticks old. You should get the world you pressed
        Start on, not the one that was running while you read the menu.

        The engine thread starts paused (`EngineStatus.PAUSED`), so this
        serves frames of a still world until something asks it to run.
        """
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._engine.run, name="sim-engine", daemon=True)
            self._thread.start()
        self._pump.start()
        self._begin_run()
        LOG.info("simulation.ready", seed=self.config.seed, population=self.state().population)

    async def start(self) -> None:
        """Run the world, booting it first if nobody has yet."""
        await self.boot()

        await self._submit(Start())
        LOG.info(
            "simulation.started",
            seed=self.config.seed,
            population=self._engine.snapshot().population,
            resources=self._engine.snapshot().resources,
        )

    async def shutdown(self) -> None:
        """Stop the pump, then the engine thread, then close the run off."""
        await self._pump.stop()

        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            self._engine.submit(Shutdown())
            await asyncio.to_thread(thread.join, 3.0)
        tick = self._engine.snapshot().tick
        if self._archive is not None:
            self._archive.end(tick)
        LOG.info("simulation.stopped", tick=tick)

    # --------------------------------------------------------------- pub/sub

    def subscribe(self, subscriber: Subscriber) -> None:
        """Register an async callback that receives every envelope."""
        self._pump.subscribe(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        """Remove a previously registered callback."""
        self._pump.unsubscribe(subscriber)

    async def broadcast(self, envelope: Envelope) -> None:
        """Send `envelope` to every subscriber."""
        await self._pump.broadcast(envelope)

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

    def tournament(self) -> TournamentReport:
        """Standings for the Axelrod preset, read under the engine lock."""
        system = self._bundle.tournament
        with self._engine.read_world() as world:
            active = world.config.tournament_mode
            standings = system.state.average_by_strategy(world) if active else {}
            # Keyed by plain `str`: the standings come from the system as
            # strings, and `StrategyName` is a Literal that will not take one.
            members: Counter[str] = Counter(str(agent.strategy) for agent in world.living_agents())
        return TournamentReport(
            active=active,
            generation=system.state.generation,
            generations=system.generations,
            finished=system.state.finished,
            pairings_played=system.state.pair_index,
            pairings_total=len(system.state.pairs),
            standings=[
                (name, score, members.get(name, 0))
                for name, score in sorted(standings.items(), key=lambda item: -item[1])
            ],
        )

    def llm_status(self) -> LLMStatus:
        """Return LLM gateway status for the health endpoint."""
        return self._gateway.status()

    def recent_events(
        self, limit: int = 100, event_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Return the newest events, newest first, optionally filtered."""
        return self._pump.recent_events(limit=limit, event_type=event_type)

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
        self._pump.clear()
        self._last_sampled_tick = -1
        # Deliberations in flight belong to the world being thrown away. The
        # broker also stamps a world uid, so a reply that is already on its
        # way back is dropped rather than applied to the new world.
        self._bundle.broker.clear()
        if self._metrics is not None:
            self._metrics.clear()
        state = await self._submit(Reset(seed=seed, config=config))
        self._begin_run()
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
        self._pump.clear()
        self._last_sampled_tick = -1
        self._bundle.broker.clear()
        if self._metrics is not None:
            self._metrics.clear()

        def build(builder: WorldBuilder) -> World:
            return load_world(payload, builder, self._bundle.minds, self._bundle.ledger)

        sequence = self._engine.submit(Restore(build))
        await self._await_sequence(sequence)
        state = self.state()
        self._begin_run()
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

    def _begin_run(self) -> None:
        """Tell the archive a new world exists, so its rows are stamped with it.

        Called wherever a world is born - startup, reset and restore - rather
        than once at construction, because every one of those is a different
        run of a different world and mixing their metrics would be nonsense.
        """
        if self._archive is None:
            return
        config = self.config
        self._archive.begin(seed=config.seed, config_json=config.model_dump_json())

    # ----------------------------------------------------- per-frame policy

    async def _on_frame(self, frame: WorldFrame) -> None:
        """What happens once per broadcast frame, besides broadcasting.

        Both of these are *policies*, not transport, which is why they stayed
        here when the pump moved out: one decides how often agents may think,
        the other decides when to sample the charts.
        """
        self._apply_speed_policy(frame.speed)
        await self._maybe_sample(frame.tick)

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
