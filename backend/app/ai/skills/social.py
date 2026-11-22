"""Getting along: Talk, Share, ProposeAlliance, Trade (SPEC section 7.3)."""

import numpy as np
from pydantic import BaseModel, ConfigDict

from app.ai import social
from app.ai.brains.base import DecisionContext
from app.ai.skills.base import Requirement, Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import need_urgency, stop
from app.core.result import OK_NONE, Err, Result
from app.core.world_config import StrategyName, WorldConfig
from app.sim import balance
from app.sim.entities import Agent, AgentState, LifeStage, Traits
from app.sim.events import EventType, SimEvent
from app.sim.names import make_name
from app.sim.world import INTERACTION_RADIUS, World

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


TALK_DURATION = 2.5
SHARE_AMOUNT = 1.0
ALLY_TRUST_REQUIRED = 0.45
TRADE_RADIUS = INTERACTION_RADIUS


class TargetParams(BaseModel):
    """Who to do this to; defaults to the nearest suitable neighbour."""

    model_config = ConfigDict(extra="forbid")

    target: int | None = None


def nearby_agents(world: World, agent: Agent, radius: float = INTERACTION_RADIUS) -> list[Agent]:
    """Living neighbours within `radius`, in stable id order."""
    found: list[Agent] = []
    for other_id in sorted(world.agent_index.neighbours(agent.id, radius)):
        other = world.agents.get(other_id)
        if other is not None and other.alive:
            found.append(other)
    return found


def resolve_target(world: World, agent: Agent, params: BaseModel) -> Agent | None:
    """Return the requested neighbour, or the nearest one."""
    if isinstance(params, TargetParams) and params.target is not None:
        other = world.agents.get(params.target)
        return other if other is not None and other.alive else None
    neighbours = nearby_agents(world, agent)
    return neighbours[0] if neighbours else None


class Talk(Skill):
    """Pass the time with someone. Builds a little trust, feeds the social need."""

    name = "Talk"
    description = "Chat with a nearby agent."
    category = SkillCategory.SOCIAL
    requires = frozenset({Requirement.NEARBY_AGENTS})
    Params = TargetParams
    visual_state = AgentState.TALK
    cooldown = 6.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require someone to talk to."""
        if resolve_target(world, agent, params) is None:
            return Err("nobody nearby")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Sociable agents want company; everyone wants it eventually."""
        if ctx.observation is not None and not ctx.observation.has_company:
            return 0.0
        return need_urgency(agent.needs.social) * (0.25 + 0.6 * agent.traits.sociability)

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Turn towards whoever we are talking to."""
        other = resolve_target(world, agent, params)
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"target": -1 if other is None else other.id},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Talk for a few seconds, then part on slightly better terms."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        other = world.agents.get(int(run.state["target"]))
        if other is None or not other.alive:
            return SkillStatus.FAILED
        if run.elapsed < TALK_DURATION:
            return SkillStatus.RUNNING

        minds = self.services.minds
        for speaker, listener in ((agent, other), (other, agent)):
            relationship = minds.require(speaker.id).memory.relationship(listener.id)
            social.adjust_trust(relationship, 0.04)
            speaker.needs.social = min(balance.NEED_MAX, speaker.needs.social + 25.0)
        return SkillStatus.DONE


class Share(Skill):
    """Give food away. The cheapest way to buy trust, and it is not cheap."""

    name = "Share"
    description = "Give food to a nearby agent."
    category = SkillCategory.SOCIAL
    requires = frozenset({Requirement.NEARBY_AGENTS})
    Params = TargetParams
    visual_state = AgentState.TRADE
    cooldown = 15.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require spare food and a hungrier neighbour."""
        if agent.inventory.food < SHARE_AMOUNT + 0.5:
            return Err("not enough food to spare")
        other = resolve_target(world, agent, params)
        if other is None:
            return Err("nobody nearby")
        if other.needs.hunger > agent.needs.hunger:
            return Err("they are better fed than I am")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Loyal, honest, well-fed agents give things away."""
        if agent.inventory.food < SHARE_AMOUNT + 0.5:
            return 0.0
        generosity = agent.traits.loyalty * 0.5 + (1.0 - agent.traits.greed) * 0.5
        comfort = agent.needs.hunger / balance.NEED_MAX
        return 0.35 * generosity * comfort

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Hand the food over immediately; the run is just the gesture."""
        other = resolve_target(world, agent, params)
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"target": -1 if other is None else other.id, "given": False},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Transfer the food and record the kindness on both sides."""
        agent = world.agents[run.agent_id]
        other = world.agents.get(int(run.state["target"]))
        if other is None or not other.alive or agent.inventory.food < SHARE_AMOUNT:
            return SkillStatus.FAILED

        amount = min(SHARE_AMOUNT, agent.inventory.food)
        agent.inventory.food -= amount
        other.inventory.food += amount

        services = self.services
        receiver = services.minds.require(other.id).memory.relationship(agent.id)
        social.adjust_trust(receiver, social.GIFT_TRUST)
        social.remember(
            services.minds.require(other.id).memory,
            tick=world.clock.tick,
            sim_seconds=world.clock.sim_seconds,
            event_type=EventType.GIFT,
            summary=f"{agent.name} gave me food",
            actors=(agent.id,),
            importance=6,
        )
        services.ledger.gifts += 1

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.GIFT,
                summary=f"{agent.name} gave food to {other.name}",
                actors=(agent.id, other.id),
                importance=4,
                position=agent.position,
            )
        )
        return SkillStatus.DONE


class ProposeAlliance(Skill):
    """Offer a pact. Accepted only if the other side already trusts you."""

    name = "ProposeAlliance"
    description = "Offer an alliance to someone you trust."
    category = SkillCategory.SOCIAL
    requires = frozenset({Requirement.NEARBY_AGENTS})
    Params = TargetParams
    visual_state = AgentState.TALK
    cooldown = 40.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a trusted neighbour who is not already an ally."""
        other = resolve_target(world, agent, params)
        if other is None:
            return Err("nobody nearby")
        mine = self.services.minds.require(agent.id).memory.social.get(other.id)
        if mine is None or mine.trust < ALLY_TRUST_REQUIRED:
            return Err("I do not trust them enough")
        if mine.is_ally:
            return Err("already allied")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Worth doing when someone nearby is already a firm friend."""
        best = 0.0
        for other_id, relationship in ctx.memory.social.items():
            if relationship.is_ally or relationship.trust < ALLY_TRUST_REQUIRED:
                continue
            if ctx.observation is not None and other_id not in ctx.observation.visible_agents:
                continue
            best = max(best, relationship.trust)
        return best * 0.5 * (0.4 + agent.traits.sociability)

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Make the offer."""
        other = resolve_target(world, agent, params)
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"target": -1 if other is None else other.id},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """They accept if they trust you back."""
        agent = world.agents[run.agent_id]
        other = world.agents.get(int(run.state["target"]))
        if other is None or not other.alive:
            return SkillStatus.FAILED

        minds = self.services.minds
        theirs = minds.require(other.id).memory.relationship(agent.id)
        if theirs.trust < ALLY_TRUST_REQUIRED:
            return SkillStatus.FAILED

        mine = minds.require(agent.id).memory.relationship(other.id)
        mine.is_ally = True
        theirs.is_ally = True
        self.services.ledger.alliances += 1

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.ALLIANCE,
                summary=f"{agent.name} and {other.name} formed an alliance",
                actors=(agent.id, other.id),
                importance=7,
                position=agent.position,
            )
        )
        return SkillStatus.DONE


class Trade(Skill):
    """An Ultimatum game: offer a split, and they take it or refuse."""

    name = "Trade"
    description = "Offer a trade; a greedy offer may be refused out of spite."
    category = SkillCategory.SOCIAL
    requires = frozenset({Requirement.NEARBY_AGENTS})
    Params = TargetParams
    visual_state = AgentState.TRADE
    cooldown = 25.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require goods and a partner."""
        if agent.inventory.food < 2.0:
            return Err("nothing worth trading")
        if resolve_target(world, agent, params) is None:
            return Err("nobody nearby")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Greedy agents like proposing splits; they get to choose the split."""
        if agent.inventory.food < 2.0:
            return 0.0
        return 0.22 * (0.3 + agent.traits.greed) * (0.4 + agent.traits.sociability)

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Decide the offer: greed sets how little the other side gets."""
        other = resolve_target(world, agent, params)
        stop(agent)
        offer = max(0.1, 0.5 - agent.traits.greed * 0.4)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"target": -1 if other is None else other.id, "offer": offer},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """A lowball offer is refused, and the refusal costs the proposer."""
        agent = world.agents[run.agent_id]
        other = world.agents.get(int(run.state["target"]))
        if other is None or not other.alive:
            return SkillStatus.FAILED

        offer = float(run.state["offer"])
        pot = min(2.0, agent.inventory.food)
        services = self.services
        theirs = services.minds.require(other.id).memory.relationship(agent.id)

        # Spite: a hungry or proud responder rejects an unfair split even
        # though accepting would leave them better off. That is the game.
        fairness_demanded = 0.25 + 0.2 * (1.0 - other.traits.greed)
        if offer < fairness_demanded:
            social.adjust_trust(theirs, -0.15)
            world.events.emit(
                SimEvent(
                    tick=world.clock.tick,
                    type=EventType.TRADE,
                    summary=f"{other.name} refused {agent.name}'s stingy offer",
                    actors=(agent.id, other.id),
                    importance=4,
                    position=agent.position,
                )
            )
            return SkillStatus.DONE

        share = pot * offer
        agent.inventory.food -= share
        other.inventory.food += share
        social.adjust_trust(theirs, 0.1)
        services.ledger.trades += 1
        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.TRADE,
                summary=f"{agent.name} and {other.name} struck a deal",
                actors=(agent.id, other.id),
                importance=3,
                position=agent.position,
            )
        )
        return SkillStatus.DONE


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
