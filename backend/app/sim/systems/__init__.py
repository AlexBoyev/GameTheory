"""The tick pipeline and the pure world systems.

Systems that need an agent's mind (perception, decisions, running skills) live
in `app.ai.systems` instead: `ai/` may read `sim/`, never the reverse
(ADR 0001).
"""

from app.sim.systems.base import System, SystemPipeline, WorldAware
from app.sim.systems.lifecycle import LifecycleSystem
from app.sim.systems.movement import MovementSystem
from app.sim.systems.needs import NeedsSystem
from app.sim.systems.regrowth import RegrowthSystem

__all__ = [
    "LifecycleSystem",
    "MovementSystem",
    "NeedsSystem",
    "RegrowthSystem",
    "System",
    "SystemPipeline",
    "WorldAware",
]
