"""The `Brain` seam and the decision trace shown in the inspector."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.ai.memory import AgentMemory
from app.ai.perception import Observation
from app.sim.entities import Agent
from app.sim.world import World


@dataclass(frozen=True, slots=True)
class ScoredOption:
    """One candidate action and why it scored what it scored."""

    skill: str
    score: float
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Decision:
    """What the brain chose, plus the runners-up for the UI.

    Attributes:
        skill: Chosen skill name.
        params: Parameters for that skill.
        options: Top candidates (SPEC section 7.4 wants the top 3).
        reason: Short explanation, surfaced as the agent's `thought`.
        from_intention: True when an LLM plan biased this choice.
    """

    skill: str
    params: dict[str, Any] = field(default_factory=dict)
    options: tuple[ScoredOption, ...] = ()
    reason: str = ""
    from_intention: bool = False


@dataclass(slots=True)
class DecisionContext:
    """Everything a brain is allowed to look at when deciding.

    Attributes:
        agent: Who is deciding.
        world: The world, for spatial queries and the clock.
        observation: What the agent last perceived; `None` before its first.
        memory: Its episodic and social memory.
        unavailable: Skill names on cooldown, which the brain must not pick.
        intention_skills: Skills an LLM plan wants (Phase 5).
        intention_bonus: Score added to those skills.
        current_skill: What the agent is already doing, if anything.
        commitment_bonus: Score added to `current_skill`, so an agent does
            not abandon a long errand for a marginally better idea. Without
            it, anything that takes more than one review interval - walking
            to a distant tree, say - never finishes.
        facts: Cheap truths about this agent, used to skip skills that cannot
            possibly run (see `ai.skills.base.Requirement`).
    """

    agent: Agent
    world: World
    memory: AgentMemory
    observation: Observation | None = None
    unavailable: frozenset[str] = frozenset()
    intention_skills: tuple[str, ...] = ()
    intention_bonus: float = 0.0
    current_skill: str | None = None
    commitment_bonus: float = 0.0
    facts: frozenset[str] = frozenset()


class Brain(Protocol):
    """Chooses the next skill for an agent.

    Must be deterministic given the same context and RNG stream.
    """

    name: str

    def decide(self, ctx: DecisionContext) -> Decision:
        """Return the chosen skill plus the decision trace."""
        ...
