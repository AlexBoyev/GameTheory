"""Working on a person directly: persuasion, bribery, betrayal (SPEC 6).

Unlike `deception`, none of these involve a third party - they are things one
agent does to another's trust, face to face.
"""

from pydantic import BaseModel

from app.ai import social
from app.ai.brains.base import DecisionContext
from app.ai.skills.base import Requirement, Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import stop
from app.ai.skills.manipulation import BRIBE_AMOUNT, GOSSIP_DURATION
from app.ai.skills.targeting import TargetParams, nearby_agents, resolve_target
from app.core.result import OK_NONE, Err, Result
from app.sim.entities import Agent, AgentState
from app.sim.events import EventType, SimEvent
from app.sim.world import World


class Persuade(Skill):
    """Talk someone round. Charisma against stubbornness."""

    name = "Persuade"
    description = "Use charisma to improve how someone sees you."
    category = SkillCategory.MANIPULATION
    requires = frozenset({Requirement.NEARBY_AGENTS})
    Params = TargetParams
    visual_state = AgentState.SCHEME
    cooldown = 30.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require someone to work on."""
        if resolve_target(world, agent, params) is None:
            return Err("nobody nearby")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Charismatic agents lean on it, especially when disliked."""
        if ctx.observation is not None and not ctx.observation.has_company:
            return 0.0
        disliked = 0.0
        for other_id, relationship in ctx.memory.social.items():
            if ctx.observation is not None and other_id not in ctx.observation.visible_agents:
                continue
            disliked = max(disliked, -relationship.trust)
        return 0.3 * agent.traits.charisma * (0.3 + disliked)

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Start talking."""
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
        """Charisma versus their loyalty to their own judgement."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        if run.elapsed < GOSSIP_DURATION:
            return SkillStatus.RUNNING

        other = world.agents.get(int(run.state["target"]))
        if other is None or not other.alive:
            return SkillStatus.FAILED

        stubbornness = 0.3 + 0.7 * other.traits.loyalty
        shift = 0.3 * agent.traits.charisma * (1.0 - stubbornness)
        relationship = self.services.minds.require(other.id).memory.relationship(agent.id)
        social.adjust_trust(relationship, shift)
        return SkillStatus.DONE


class Bribe(Skill):
    """Buy goodwill with food. Crude, effective, and remembered."""

    name = "Bribe"
    description = "Give food specifically to buy someone's trust."
    category = SkillCategory.MANIPULATION
    requires = frozenset({Requirement.NEARBY_AGENTS})
    Params = TargetParams
    visual_state = AgentState.SCHEME
    cooldown = 45.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require food to spend and someone worth spending it on."""
        if agent.inventory.food < BRIBE_AMOUNT + 1.0:
            return Err("cannot afford a bribe")
        if resolve_target(world, agent, params) is None:
            return Err("nobody nearby")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Cunning agents with spare food buy friends."""
        if agent.inventory.food < BRIBE_AMOUNT + 1.0:
            return 0.0
        return 0.25 * agent.traits.cunning * (1.0 - agent.traits.honesty)

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Offer the food."""
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
        """Hand it over; trust bought is trust all the same."""
        agent = world.agents[run.agent_id]
        other = world.agents.get(int(run.state["target"]))
        if other is None or not other.alive or agent.inventory.food < BRIBE_AMOUNT:
            return SkillStatus.FAILED

        agent.inventory.food -= BRIBE_AMOUNT
        other.inventory.food += BRIBE_AMOUNT
        relationship = self.services.minds.require(other.id).memory.relationship(agent.id)
        social.adjust_trust(relationship, social.GIFT_TRUST * 1.4)

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.GIFT,
                summary=f"{agent.name} bribed {other.name}",
                actors=(agent.id, other.id),
                importance=5,
                position=agent.position,
            )
        )
        return SkillStatus.DONE


class Betray(Skill):
    """Rob someone who trusts you. The most expensive thing an agent can do."""

    name = "Betray"
    description = "Steal from someone who trusts you."
    category = SkillCategory.MANIPULATION
    requires = frozenset({Requirement.NEARBY_AGENTS})
    Params = TargetParams
    visual_state = AgentState.SCHEME
    cooldown = 60.0

    MIN_TRUST = 0.35

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a trusting victim with something worth taking."""
        victim = self._victim(agent, world, params)
        if victim is None:
            return Err("nobody trusts me enough to betray")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Greed and dishonesty, scaled by hunger - desperation tempts."""
        appetite = agent.traits.greed * (1.0 - agent.traits.honesty) * agent.traits.cunning
        hunger = 1.0 - agent.needs.hunger / 100.0
        return 0.55 * appetite * (0.4 + hunger)

    def _victim(self, agent: Agent, world: World, params: BaseModel) -> Agent | None:
        """Someone nearby who trusts us and is carrying something."""
        minds = self.services.minds
        if isinstance(params, TargetParams) and params.target is not None:
            candidate = world.agents.get(params.target)
            candidates = [candidate] if candidate is not None else []
        else:
            candidates = nearby_agents(world, agent)

        for other in candidates:
            if other is None or not other.alive or other.inventory.food <= 0.5:
                continue
            theirs = minds.require(other.id).memory.social.get(agent.id)
            if theirs is not None and theirs.trust >= self.MIN_TRUST:
                return other
        return None

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Pick the mark."""
        victim = self._victim(agent, world, params)
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"victim": -1 if victim is None else victim.id},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Take everything, and lose them forever."""
        agent = world.agents[run.agent_id]
        victim = world.agents.get(int(run.state["victim"]))
        if victim is None or not victim.alive:
            return SkillStatus.FAILED

        taken = victim.inventory.food
        victim.inventory.food = 0.0
        agent.inventory.food += taken

        services = self.services
        theirs = services.minds.require(victim.id).memory.relationship(agent.id)
        social.adjust_trust(theirs, social.BETRAYAL_TRUST)
        theirs.betrayals += 1
        theirs.is_ally = False
        social.remember(
            services.minds.require(victim.id).memory,
            tick=world.clock.tick,
            sim_seconds=world.clock.sim_seconds,
            event_type=EventType.BETRAYAL,
            summary=f"{agent.name} robbed me",
            actors=(agent.id,),
            importance=10,
        )
        services.ledger.betrayals += 1

        # Betrayal is public: everyone who can see it hears about it.
        for witness in nearby_agents(world, victim):
            if witness.id == agent.id:
                continue
            belief = services.minds.require(witness.id).memory.relationship(agent.id)
            belief.reputation = social.clamp_trust(belief.reputation - 0.3)

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.BETRAYAL,
                summary=f"{agent.name} betrayed {victim.name} and took {taken:.1f} food",
                actors=(agent.id, victim.id),
                importance=9,
                position=agent.position,
            )
        )
        return SkillStatus.DONE
