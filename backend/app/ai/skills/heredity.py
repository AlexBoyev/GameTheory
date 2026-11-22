"""Making a child: whose traits it gets, and what it plays (SPEC 4.3).

Separate from the rest of the social skills because inheritance is its own
subject - blending two personalities and mutating a strategy is the only place
in the simulation where a new agent's character comes from somewhere.
"""

import numpy as np
from pydantic import BaseModel

from app.ai.brains.base import DecisionContext
from app.ai.skills.base import Requirement, Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import stop
from app.ai.skills.targeting import TargetParams, nearby_agents
from app.core.result import OK_NONE, Err, Result
from app.core.world_config import StrategyName, WorldConfig
from app.sim import balance
from app.sim.entities import Agent, AgentState, LifeStage, Traits
from app.sim.events import EventType, SimEvent
from app.sim.names import make_name
from app.sim.world import World

TRAIT_NAMES: tuple[str, ...] = (
    "aggression",
    "honesty",
    "loyalty",
    "greed",
    "sociability",
    "cunning",
    "courage",
    "charisma",
)


def blend_traits(
    first: Traits,
    second: Traits,
    rng: "np.random.Generator",
    mutation_rate: float,
) -> Traits:
    """Average the parents, then jitter - inheritance with room to drift."""
    values: dict[str, float] = {}
    for name in TRAIT_NAMES:
        mean = (getattr(first, name) + getattr(second, name)) / 2.0
        if float(rng.random()) < mutation_rate:
            mean += float(rng.normal(0.0, 0.18))
        values[name] = max(0.0, min(1.0, mean))
    return Traits(**values)


def inherit_strategy(
    first: Agent,
    second: Agent,
    rng: "np.random.Generator",
    config: WorldConfig,
) -> StrategyName:
    """Take one parent's gene, or mutate into a different one entirely.

    Mutation is what stops a world converging on one strategy and staying
    there - it is the only source of new genes once the island is populated.
    """
    if float(rng.random()) < config.mutation_rate:
        pool = sorted(config.normalised_strategy_mix)
        return pool[int(rng.integers(len(pool)))]
    return first.strategy if bool(rng.integers(2)) else second.strategy


class Reproduce(Skill):
    """Have a child with a trusted partner (SPEC 4.2)."""

    name = "Reproduce"
    description = "Have a child with a partner you both trust."
    category = SkillCategory.SOCIAL
    requires = frozenset({Requirement.NEARBY_AGENTS})
    Params = TargetParams
    visual_state = AgentState.TALK
    cooldown = 240.0

    MIN_FOOD = 2.0
    MIN_TRUST = 0.35
    MIN_AGE = 18.0
    MAX_AGE = 48.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require two willing, well-fed adults and room in the world."""
        if len(world.agents) >= world.config.max_agents:
            return Err("the island is full")
        if not (self.MIN_AGE <= agent.age <= self.MAX_AGE):
            return Err("not of age")
        if agent.inventory.food < self.MIN_FOOD or agent.needs.hunger < 55.0:
            return Err("not well fed enough")
        partner = self._partner(agent, world, params)
        if partner is None:
            return Err("no willing partner nearby")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Comfortable, sociable adults with a trusted partner nearby."""
        if agent.needs.hunger < 55.0 or not (self.MIN_AGE <= agent.age <= self.MAX_AGE):
            return 0.0
        comfort = min(agent.needs.hunger, agent.needs.thirst) / balance.NEED_MAX
        return 0.3 * comfort * (0.3 + agent.traits.sociability)

    def _partner(self, agent: Agent, world: World, params: BaseModel) -> Agent | None:
        """A nearby adult who trusts us and whom we trust."""
        minds = self.services.minds
        mine = minds.require(agent.id).memory
        for other in nearby_agents(world, agent):
            if not (self.MIN_AGE <= other.age <= self.MAX_AGE):
                continue
            ours = mine.social.get(other.id)
            theirs = minds.require(other.id).memory.social.get(agent.id)
            if ours is None or theirs is None:
                continue
            if ours.trust >= self.MIN_TRUST and theirs.trust >= self.MIN_TRUST:
                return other
        return None

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Pair off."""
        partner = self._partner(agent, world, params)
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"partner": -1 if partner is None else partner.id},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Blend the parents into a child and put it on the island."""
        agent = world.agents[run.agent_id]
        partner = world.agents.get(int(run.state["partner"]))
        if partner is None or not partner.alive:
            return SkillStatus.FAILED
        if len(world.agents) >= world.config.max_agents:
            return SkillStatus.FAILED

        rng = world.rngs["spawn"]
        agent.inventory.food -= 1.0
        partner.inventory.food = max(0.0, partner.inventory.food - 1.0)

        child = Agent(
            id=world.next_agent_id,
            name=make_name(rng, {other.name for other in world.agents.values()}),
            position=agent.position,
            traits=blend_traits(agent.traits, partner.traits, rng, world.config.mutation_rate),
            strategy=inherit_strategy(agent, partner, rng, world.config),
            brain_type=agent.brain_type if bool(rng.integers(2)) else partner.brain_type,
            age=0.0,
            life_stage=LifeStage.CHILD,
            tribe_id=agent.tribe_id if agent.tribe_id is not None else partner.tribe_id,
            born_tick=world.clock.tick,
        )
        world.agents[child.id] = child
        world.next_agent_id += 1
        world.births += 1
        world.invalidate_living()
        world.agent_index.insert(child.id, child.position[0], child.position[1])
        if child.tribe_id is not None and child.tribe_id in world.tribes:
            world.tribes[child.tribe_id].member_ids.add(child.id)

        self.services.ledger.births += 1
        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.BIRTH,
                summary=f"{child.name} was born to {agent.name} and {partner.name}",
                actors=(child.id, agent.id, partner.id),
                importance=7,
                position=agent.position,
                data={"strategy": child.strategy},
            )
        )
        return SkillStatus.DONE
