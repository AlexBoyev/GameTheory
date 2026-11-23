"""Getting along: Talk, Share, ProposeAlliance, Trade (SPEC section 7.3)."""

from pydantic import BaseModel

from app.ai import social
from app.ai.brains.base import DecisionContext
from app.ai.skills.base import (
    Consideration,
    Requirement,
    Skill,
    SkillCategory,
    SkillRun,
    SkillStatus,
)
from app.ai.skills.helpers import need_urgency, stop
from app.ai.skills.targeting import TargetParams, resolve_target
from app.core.result import OK_NONE, Err, Result
from app.sim import balance
from app.sim.entities import Agent, AgentState
from app.sim.events import EventType, SimEvent
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


TALK_DURATION = 2.5
SHARE_AMOUNT = 1.0
ALLY_TRUST_REQUIRED = 0.45
TRADE_RADIUS = INTERACTION_RADIUS


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

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Sociable agents want company; everyone wants it eventually."""
        if ctx.observation is not None and not ctx.observation.has_company:
            return []
        return [
            Consideration(
                "lonely",
                need_urgency(agent.needs.social),
                0.25 + 0.6 * agent.traits.sociability,
            )
        ]

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

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Loyal, honest, well-fed agents give things away."""
        if agent.inventory.food < SHARE_AMOUNT + 0.5:
            return []
        generosity = agent.traits.loyalty * 0.5 + (1.0 - agent.traits.greed) * 0.5
        comfort = agent.needs.hunger / balance.NEED_MAX
        return [Consideration("feeling generous", generosity * comfort, 0.35)]

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

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Worth doing when someone nearby is already a firm friend."""
        best = 0.0
        for other_id, relationship in ctx.memory.social.items():
            if relationship.is_ally or relationship.trust < ALLY_TRUST_REQUIRED:
                continue
            if ctx.observation is not None and other_id not in ctx.observation.visible_agents:
                continue
            best = max(best, relationship.trust)
        return [Consideration("a firm friend nearby", best, 0.5 * (0.4 + agent.traits.sociability))]

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

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Greedy agents like proposing splits; they get to choose the split.

        A constant value with everything in the weight, because both factors
        can exceed 1 and neither is the "reason" - the appetite for a bargain
        simply is the product of the two traits.
        """
        if agent.inventory.food < 2.0:
            return []
        weight = 0.22 * (0.3 + agent.traits.greed) * (0.4 + agent.traits.sociability)
        return [Consideration("fancies a bargain", 1.0, weight)]

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
