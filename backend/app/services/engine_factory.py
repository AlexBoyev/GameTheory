"""Assembling the engine: the one place `sim/` and `ai/` are wired together.

`sim/` provides the world and the pure systems; `ai/` provides the systems
that need minds. Neither imports the other - this module, in the service
layer, knows about both (ADR 0001).
"""

from dataclasses import dataclass

from app.ai.brains.utility_brain import UtilityBrain
from app.ai.minds import MindRegistry
from app.ai.skills.registry import SkillRegistry, build_registry
from app.ai.systems import DecisionSystem, PerceptionSystem, SkillExecutionSystem
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
    minds: MindRegistry, skills: SkillRegistry, temperature: float
) -> SystemPipeline:
    """Return the tick pipeline in its documented running order (SPEC 7.1).

    Order is load-bearing: perception feeds the decision, the decision starts
    the skill, the skill sets a velocity, and only then does movement apply it.
    Reordering these changes behaviour, so the list is explicit.
    """
    brain = UtilityBrain(skills, temperature=temperature)
    return SystemPipeline(
        (
            PerceptionSystem(minds),
            NeedsSystem(),
            DecisionSystem(minds, brain, skills),
            SkillExecutionSystem(minds, skills),
            MovementSystem(),
            RegrowthSystem(),
            LifecycleSystem(),
        )
    )


def build_engine_bundle(
    settings: Settings,
    config: WorldConfig | None = None,
    pacer: Pacer | None = None,
) -> EngineBundle:
    """Build a fully wired engine (not yet running)."""
    skills = build_registry()
    minds = MindRegistry()
    pipeline = build_pipeline(minds, skills, settings.sim_softmax_temperature)

    engine = SimulationEngine(
        config=config or world_config_from_settings(settings),
        builder=IslandWorldBuilder(),
        pacer=pacer or MonotonicPacer(),
        pipeline=pipeline,
        frame_hz=settings.sim_broadcast_hz,
    )
    return EngineBundle(engine=engine, minds=minds, skills=skills)
