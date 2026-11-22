"""The `Skill` contract (SPEC section 7.3).

One class per action, shared by the utility brain and the LLM: `check()` gates
it, `utility()` scores it, `start()`/`step()` run it over several ticks. The
`Params` model doubles as the JSON schema handed to the LLM.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance
    from app.ai.skill_services import SkillServices

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


class Requirement(StrEnum):
    """A cheap fact about an agent that a skill cannot run without.

    The utility brain scores every registered skill on every decision, and
    most of them are ruled out before any arithmetic: a tribeless agent alone
    in a field cannot possibly gossip, raid, store food or declare war. Each
    skill declares the facts it needs, the brain computes them once, and the
    impossible ones never get a `check()` call - which was 44% of runtime at
    500 agents.

    The rule these must obey: **if a requirement is unmet, `check()` must fail
    too.** A requirement is a cheap pre-test of something `check()` already
    enforces, never a new condition. `test_requirements_are_safe` asserts
    exactly that against a running world, because getting it wrong would
    silently disable a skill with no error anywhere.
    """

    NEARBY_AGENTS = "nearby_agents"
    """Somebody else is in sight. A conservative superset of the interaction
    radius: if nobody is visible at vision range, nobody is within 4 units."""

    IN_TRIBE = "in_tribe"
    TRIBELESS = "tribeless"
    TRIBE_LEADER = "tribe_leader"


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

    requires: ClassVar[frozenset[Requirement]] = frozenset()
    """Facts without which this skill cannot run (see `Requirement`).

    Declaring none is always correct and merely slower; declaring one that
    `check()` does not enforce is a bug, and there is a test for it."""

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

    _services: "SkillServices | None" = None

    def bind(self, services: "SkillServices") -> None:
        """Receive the collaborators a social skill needs.

        Called once by the registry. Held per instance rather than in a
        module global, so two registries (a test and the engine, say) never
        share state.
        """
        self._services = services

    @property
    def services(self) -> "SkillServices":
        """The bound services, or a clear error if the skill was never bound."""
        if self._services is None:
            msg = f"{type(self).name} was used before SkillRegistry bound its services"
            raise RuntimeError(msg)
        return self._services

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
