"""Assembling the engine: the one place `sim/` and `ai/` are wired together.

`sim/` provides the world and the pure systems; `ai/` provides the systems
that need minds. Neither imports the other - this module, in the service
layer, knows about both (ADR 0001).
"""

from dataclasses import dataclass
from pathlib import Path

from app.ai.brains.utility_brain import UtilityBrain
from app.ai.gametheory.ledger import SocialLedger
from app.ai.gametheory.payoffs import PayoffConfig, load_payoffs
from app.ai.gametheory.resolver import EncounterResolver
from app.ai.gametheory.strategies import build_strategy_registry
from app.ai.llm.broker import IntentionBroker
from app.ai.minds import MindRegistry
from app.ai.skill_services import SkillServices
from app.ai.skills.registry import SkillRegistry, build_registry
from app.ai.systems import DecisionSystem, PerceptionSystem, SkillExecutionSystem
from app.ai.systems.encounter_system import EncounterSystem
from app.ai.systems.intention_system import IntentionSystem
from app.ai.systems.tribe_system import TribeSystem
from app.core.settings import Settings
from app.core.world_config import WorldConfig
from app.services.pacer import MonotonicPacer
from app.sim.engine import Pacer, SimulationEngine
from app.sim.systems import (
    LifecycleSystem,
    MovementSystem,
    NeedsSystem,
    RegrowthSystem,
    SystemPipeline,
)
from app.sim.worldgen import IslandWorldBuilder


@dataclass(frozen=True, slots=True)
class EngineBundle:
    """The engine plus the pieces the API needs to answer questions about it."""

    engine: SimulationEngine
    minds: MindRegistry
    skills: SkillRegistry
    ledger: SocialLedger
    payoffs: PayoffConfig
    broker: IntentionBroker


def world_config_from_settings(settings: Settings) -> WorldConfig:
    """Build the default `WorldConfig` from process settings."""
    return WorldConfig(
        seed=settings.sim_seed,
        max_agents=settings.sim_max_agents,
        dt=settings.sim_dt,
        day_seconds=settings.sim_day_seconds,
        days_per_season=settings.sim_days_per_season,
    )


def build_pipeline(
    minds: MindRegistry,
    skills: SkillRegistry,
    temperature: float,
    *,
    ledger: SocialLedger | None = None,
    payoffs: PayoffConfig | None = None,
    broker: IntentionBroker | None = None,
) -> SystemPipeline:
    """Return the tick pipeline in its documented running order (SPEC 7.1).

    Order is load-bearing: perception feeds the decision, the decision starts
    the skill, the skill sets a velocity, and only then does movement apply
    it. Encounters run after skills, so a game is played between agents whose
    intentions for this tick are already settled.

    Deliberation comes first of all: it installs the plans that came back from
    the model since the last tick, so a decision taken this tick can act on
    one. It never waits for the model (ADR 0004).
    """
    resolved_ledger = ledger or SocialLedger()
    resolved_payoffs = payoffs or load_payoffs()
    strategies = build_strategy_registry()
    resolver = EncounterResolver(resolved_payoffs, strategies, minds)
    brain = UtilityBrain(skills, temperature=temperature)

    # Bind here rather than at the call site: this function is the only place
    # that knows the minds and the ledger a pipeline will actually run with,
    # so it is the only place that can guarantee the skills share them.
    skills.bind(SkillServices(minds=minds, ledger=resolved_ledger))

    return SystemPipeline(
        (
            IntentionSystem(minds, skills, broker or IntentionBroker()),
            PerceptionSystem(minds),
            NeedsSystem(),
            DecisionSystem(minds, brain, skills),
            SkillExecutionSystem(minds, skills),
            EncounterSystem(minds, resolver, resolved_ledger),
            MovementSystem(),
            RegrowthSystem(),
            TribeSystem(minds, resolved_ledger),
            LifecycleSystem(),
        )
    )


def payoff_path(settings: Settings) -> Path:
    """Where the payoff matrices live."""
    return Path(settings.config_dir) / "payoffs.yaml"


def build_engine_bundle(
    settings: Settings,
    config: WorldConfig | None = None,
    pacer: Pacer | None = None,
) -> EngineBundle:
    """Build a fully wired engine (not yet running)."""
    minds = MindRegistry()
    ledger = SocialLedger()
    payoffs = load_payoffs(payoff_path(settings))
    broker = IntentionBroker()

    skills = build_registry(SkillServices(minds=minds, ledger=ledger))
    pipeline = build_pipeline(
        minds,
        skills,
        settings.sim_softmax_temperature,
        ledger=ledger,
        payoffs=payoffs,
        broker=broker,
    )

    engine = SimulationEngine(
        config=config or world_config_from_settings(settings),
        builder=IslandWorldBuilder(),
        pacer=pacer or MonotonicPacer(),
        pipeline=pipeline,
        frame_hz=settings.sim_broadcast_hz,
    )
    return EngineBundle(
        engine=engine,
        minds=minds,
        skills=skills,
        ledger=ledger,
        payoffs=payoffs,
        broker=broker,
    )
