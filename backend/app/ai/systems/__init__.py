"""Tick systems that need an agent's mind.

These live in `ai/` rather than `sim/` because they reach into memory, brains
and skills, and `sim/` must not import `ai/` (ADR 0001). They satisfy the same
`sim.systems.System` protocol, so the engine cannot tell the difference.
"""

from app.ai.systems.decision_system import DecisionSystem
from app.ai.systems.encounter_system import EncounterSystem
from app.ai.systems.perception_system import PerceptionSystem
from app.ai.systems.skill_system import SkillExecutionSystem
from app.ai.systems.tribe_system import TribeSystem

__all__ = [
    "DecisionSystem",
    "EncounterSystem",
    "PerceptionSystem",
    "SkillExecutionSystem",
    "TribeSystem",
]
