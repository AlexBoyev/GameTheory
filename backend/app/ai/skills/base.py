"""The `Skill` contract (SPEC section 7.3).

One class per action, shared by the utility brain and the LLM: `check()` gates
it, `utility()` scores it, `start()`/`step()` run it over several ticks. The
`Params` model doubles as the JSON schema handed to the LLM.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel

from app.ai.brains.base import DecisionContext
from app.core.result import Result
from app.sim.entities import Agent, AgentState
from app.sim.world import World


class SkillCategory(StrEnum):
    """Grouping used by the UI and by LLM prompt filtering."""

    SURVIVAL = "survival"
    SOCIAL = "social"
    MANIPULATION = "manipulation"
    COMBAT = "combat"
    TRIBE = "tribe"


class SkillStatus(StrEnum):
    """Result of advancing a running skill."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class NoParams(BaseModel):
    """Parameter model for skills that take no arguments."""


@dataclass(slots=True)
class SkillRun:
    """Live state of one skill execution.

    Attributes:
        skill: Skill name.
        agent_id: Who is running it.
        params: Validated parameters.
        started_tick: Tick the run began.
        elapsed: Sim-seconds spent so far.
        state: Scratch space owned by the skill.
    """

    skill: str
    agent_id: int
    params: BaseModel
    started_tick: int
    elapsed: float = 0.0
    state: dict[str, Any] = field(default_factory=dict)


class Skill(ABC):
    """Base class for every agent action.

    Subclasses set the class variables and implement the four methods. They are
    stateless: all per-run state belongs in the `SkillRun`.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    category: ClassVar[SkillCategory]
    Params: ClassVar[type[BaseModel]] = NoParams
    cooldown: ClassVar[float] = 0.0
    interruptible: ClassVar[bool] = True

    visual_state: ClassVar[AgentState] = AgentState.IDLE
    """What the agent looks like it is doing while this runs."""

    autonomous: ClassVar[bool] = True
    """False for skills only an explicit plan may call (they need real params,
    so the utility brain - which always passes defaults - must skip them)."""

    @abstractmethod
    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Return `Ok(None)` if runnable, else `Err(reason)`.

        The reason is shown in the inspector and fed back to an LLM whose plan
        referenced an impossible action.
        """

    @abstractmethod
    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Score this skill for the utility brain (higher wins)."""

    @abstractmethod
    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Begin execution and return the run handle."""

    @abstractmethod
    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Advance the run by `dt` sim-seconds."""

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return the JSON schema of `Params`, for LLM tool definitions."""
        return cls.Params.model_json_schema()

    @classmethod
    def describe(cls) -> dict[str, Any]:
        """Return a compact description for prompts and `GET /api/agents`."""
        return {
            "name": cls.name,
            "description": cls.description,
            "category": cls.category.value,
            "params": cls.params_schema(),
        }
