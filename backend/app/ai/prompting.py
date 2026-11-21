"""Turning a live agent into the plain data a prompt is rendered from.

The engine thread builds these; the event loop renders and sends them. That
split is the whole reason they exist: by the time a reply comes back the world
has moved on, so nothing here may be a reference into it. Everything is a
`str`, a number, or a list of those - never an `Agent`, a `World` or a `Mind`.

This lives in `ai/` rather than `ai/llm/` because it reads `sim/`, which
`ai/llm/` is forbidden to do. It hands over a `PromptContext` and nothing else.
"""

from typing import Any

from pydantic import ValidationError

from app.ai.llm.context import PromptContext
from app.ai.memory import AgentMemory
from app.ai.perception import Observation
from app.ai.skills.registry import SkillRegistry
from app.core.result import is_ok
from app.sim.entities import Agent
from app.sim.world import World

MAX_NEARBY = 6
MAX_MEMORIES = 6
MAX_RELATIONSHIPS = 6
MAX_SKILLS = 14
MAX_PLAN_STEPS = 3
MAX_BELIEFS = 5


def _traits(agent: Agent) -> dict[str, float]:
    """Traits as a plain mapping, in a stable order."""
    traits = agent.traits
    return {
        "aggression": traits.aggression,
        "honesty": traits.honesty,
        "loyalty": traits.loyalty,
        "greed": traits.greed,
        "sociability": traits.sociability,
        "cunning": traits.cunning,
        "courage": traits.courage,
        "charisma": traits.charisma,
    }


def _needs(agent: Agent) -> dict[str, float]:
    """Needs as a plain mapping, in a stable order."""
    needs = agent.needs
    return {
        "hunger": needs.hunger,
        "thirst": needs.thirst,
        "energy": needs.energy,
        "safety": needs.safety,
        "social": needs.social,
    }


def _nearby(
    world: World, memory: AgentMemory, observation: Observation | None
) -> list[dict[str, Any]]:
    """Who the agent can see, with what it thinks of them."""
    if observation is None:
        return []
    people: list[dict[str, Any]] = []
    for other_id in sorted(observation.visible_agents)[:MAX_NEARBY]:
        other = world.agents.get(other_id)
        if other is None or not other.alive:
            continue
        relationship = memory.social.get(other_id)
        people.append(
            {
                "name": other.name,
                "trust": relationship.trust if relationship is not None else 0.0,
            }
        )
    return people


def _relationships(world: World, memory: AgentMemory) -> list[dict[str, Any]]:
    """The strongest opinions this agent holds, friendly or otherwise."""
    known: list[dict[str, Any]] = []
    for other_id, relationship in memory.top_relationships(MAX_RELATIONSHIPS):
        other = world.agents.get(other_id)
        if other is None:
            continue
        known.append(
            {
                "name": other.name,
                "trust": relationship.trust,
                "is_ally": relationship.trust >= 0.5,
                "caught_lying": relationship.caught_lying,
            }
        )
    return known


def _memories(memory: AgentMemory, now_sim_s: float, day_seconds: float) -> list[dict[str, Any]]:
    """What the agent remembers, ranked by importance and recency."""
    return [
        {
            "summary": event.summary,
            "day": int(event.sim_seconds // day_seconds) if day_seconds > 0 else 0,
        }
        for event in memory.recall(now_sim_s, limit=MAX_MEMORIES)
    ]


def _skills(
    registry: SkillRegistry,
    agent: Agent,
    world: World,
    unavailable: frozenset[str],
) -> list[dict[str, str]]:
    """The skills worth offering, preferring ones known to be possible now.

    Offering an action whose preconditions already fail teaches the model to
    plan things that silently do nothing, so `check()` is the filter wherever
    it can be applied. It cannot be applied to a skill whose parameters are
    required (`MoveTo(x, z)` has no default target), and dropping those would
    hide half the action library from the model - so they are offered with
    their parameter hint, and `check()` still gates them when the plan is
    actually executed.
    """
    available: list[dict[str, str]] = []
    for skill in registry.all():
        definition = type(skill)
        if definition.name in unavailable:
            continue
        try:
            params = definition.Params()
        except ValidationError:
            params = None
        if params is not None and not is_ok(skill.check(agent, world, params)):
            continue
        hints = list(definition.Params.model_fields)
        available.append(
            {
                "name": definition.name,
                "description": definition.description,
                "params_hint": ", ".join(hints),
            }
        )
        if len(available) >= MAX_SKILLS:
            break
    return available


def build_intention_context(
    world: World,
    agent: Agent,
    memory: AgentMemory,
    observation: Observation | None,
    registry: SkillRegistry,
    unavailable: frozenset[str] = frozenset(),
) -> PromptContext:
    """Snapshot everything `intention.j2` needs for `agent`."""
    clock = world.clock
    tribe = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
    context: dict[str, Any] = {
        "agent": {
            "name": agent.name,
            "age": agent.age,
            "strategy": agent.strategy,
            "traits": _traits(agent),
            "needs": _needs(agent),
            "inventory": {"food": agent.inventory.food, "wood": agent.inventory.wood},
            "tribe": {"name": tribe.name} if tribe is not None else None,
            "role": agent.role.value if tribe is not None else "none",
        },
        "clock": {
            "day": clock.day,
            "season": clock.season,
            "is_night": clock.is_night,
        },
        "nearby": _nearby(world, memory, observation),
        "relationships": _relationships(world, memory),
        "memories": _memories(memory, clock.sim_seconds, clock.day_seconds),
        "skills": _skills(registry, agent, world, unavailable),
        "max_steps": MAX_PLAN_STEPS,
    }
    return PromptContext(agent_id=agent.id, kind="intention", context=context)


def build_reflection_context(world: World, agent: Agent, memory: AgentMemory) -> PromptContext:
    """Snapshot everything `reflection.j2` needs for `agent`."""
    return PromptContext(
        agent_id=agent.id,
        kind="reflection",
        context={
            "agent": {"name": agent.name},
            "memories": _memories(memory, world.clock.sim_seconds, world.clock.day_seconds),
            "max_beliefs": MAX_BELIEFS,
        },
    )
