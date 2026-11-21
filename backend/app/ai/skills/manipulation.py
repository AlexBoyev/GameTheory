"""Working people: Gossip, Lie, Persuade, Bribe, Betray (SPEC sections 6, 7.3).

The point of this file is that information is not free and not reliable. An
agent's reputation is whatever the last person to mention them said, weighted
by how much the listener trusted the teller - so a charismatic liar can
destroy someone they have never met, and get away with it until the evidence
piles up.
"""

import numpy as np
from pydantic import BaseModel, ConfigDict

from app.ai import social
from app.ai.brains.base import DecisionContext
from app.ai.skills.base import Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import stop
from app.ai.skills.social import TargetParams, nearby_agents, resolve_target
from app.core.result import OK_NONE, Err, Result
from app.sim.entities import Agent, AgentState
from app.sim.events import EventType, SimEvent
from app.sim.world import World

GOSSIP_DURATION = 2.0
BRIBE_AMOUNT = 1.5
KNOWS_BETTER_TRUST = 0.35
"""Trust in the subject above which the listener has evidence of their own."""


class GossipParams(BaseModel):
    """Who to talk to, and who to talk about."""

    model_config = ConfigDict(extra="forbid")

    target: int | None = None
    about: int | None = None
    truthful: bool | None = None


class Gossip(Skill):
    """Tell someone what you think of a third party - honestly or otherwise."""

    name = "Gossip"
    description = "Tell a neighbour your opinion of someone else."
    category = SkillCategory.MANIPULATION
    Params = GossipParams
    visual_state = AgentState.TALK
    cooldown = 18.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a listener and someone to talk about."""
        listener = resolve_target(world, agent, params)
        if listener is None:
            return Err("nobody to talk to")
        if self._subject(agent, world, listener, params) is None:
            return Err("nothing to say about anyone")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Sociable or cunning agents gossip; it costs nothing and moves worlds."""
        if ctx.observation is not None and not ctx.observation.has_company:
            return 0.0
        if len(ctx.memory.social) < 2:
            return 0.0
        appetite = 0.45 * agent.traits.sociability + 0.55 * agent.traits.cunning
        return 0.3 * appetite

    def _subject(
        self,
        agent: Agent,
        world: World,
        listener: Agent,
        params: BaseModel,
    ) -> int | None:
        """Pick who to discuss: the person we feel most strongly about."""
        if isinstance(params, GossipParams) and params.about is not None:
            return params.about
        memory = self.services.minds.require(agent.id).memory
        best: int | None = None
        strongest = 0.2
        for other_id, relationship in sorted(memory.social.items()):
            if other_id == listener.id or other_id not in world.agents:
                continue
            if abs(relationship.trust) > strongest:
                strongest, best = abs(relationship.trust), other_id
        return best

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Decide what to say, and whether it will be true."""
        listener = resolve_target(world, agent, params)
        subject = None if listener is None else self._subject(agent, world, listener, params)
        stop(agent)

        truthful = True
        if isinstance(params, GossipParams) and params.truthful is not None:
            truthful = params.truthful
        else:
            # Dishonest, cunning agents invent things.
            dishonesty = (1.0 - agent.traits.honesty) * agent.traits.cunning
            truthful = float(world.rngs["gossip"].random()) > dishonesty

        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={
                "listener": -1 if listener is None else listener.id,
                "subject": -1 if subject is None else subject,
                "truthful": truthful,
            },
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Deliver the claim; the listener weighs it by how much they trust us."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        if run.elapsed < GOSSIP_DURATION:
            return SkillStatus.RUNNING

        listener = world.agents.get(int(run.state["listener"]))
        subject_id = int(run.state["subject"])
        subject = world.agents.get(subject_id)
        if listener is None or subject is None or not listener.alive:
            return SkillStatus.FAILED

        services = self.services
        speaker_memory = services.minds.require(agent.id).memory
        listener_memory = services.minds.require(listener.id).memory

        honest_opinion = social.effective_opinion(speaker_memory, subject_id)
        truthful = bool(run.state["truthful"])
        # A lie is the opposite of what you actually believe, said with feeling.
        claim = (
            honest_opinion
            if truthful
            else -max(0.4, abs(honest_opinion)) * (1.0 if honest_opinion < 0 else -1.0)
        )

        social.apply_gossip(listener_memory, agent.id, subject_id, claim)
        services.ledger.gossip_spread += 1

        caught = False
        if not truthful:
            services.ledger.lies_told += 1
            listener_view = listener_memory.social.get(subject_id)
            knows_better = (
                listener_view is not None
                and listener_view.interactions > 0
                and abs(listener_view.trust) > KNOWS_BETTER_TRUST
            )
            chance = social.lie_detection_chance(agent.traits, listener.traits, knows_better)
            caught = float(world.rngs["gossip"].random()) < chance
            if caught:
                social.punish_caught_liar(listener_memory, agent.id)
                services.ledger.lies_caught += 1

        self._announce(world, agent, listener, subject, truthful=truthful, caught=caught)
        return SkillStatus.DONE

    @staticmethod
    def _announce(
        world: World,
        speaker: Agent,
        listener: Agent,
        subject: Agent,
        *,
        truthful: bool,
        caught: bool,
    ) -> None:
        """Put the conversation in the event feed."""
        if caught:
            kind = EventType.LIE_CAUGHT
            summary = f"{listener.name} caught {speaker.name} lying about {subject.name}"
            importance = 8
        elif truthful:
            kind = EventType.GOSSIP
            summary = f"{speaker.name} told {listener.name} about {subject.name}"
            importance = 3
        else:
            kind = EventType.LIE_TOLD
            summary = f"{speaker.name} spread a lie about {subject.name} to {listener.name}"
            importance = 6

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=kind,
                summary=summary,
                actors=(speaker.id, listener.id, subject.id),
                importance=importance,
                position=speaker.position,
            )
        )


class Lie(Skill):
    """Send someone to a patch of nothing.

    Distinct from `Gossip`, which is about people. A lie here is about the
    world: "there are berries over there". The victim walks, finds bare
    ground, and has lost the one thing nobody can get back - time.
    """

    name = "Lie"
    description = "Tell someone food is somewhere it is not."
    category = SkillCategory.MANIPULATION
    Params = TargetParams
    visual_state = AgentState.SCHEME
    cooldown = 50.0

    LEAD_DISTANCE = 45.0
    LEAD_DURATION = 90.0
    MIN_CREDULITY = -0.1
    """They have to not actively distrust you, or they will ignore it."""

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a listener who would believe it."""
        victim = self._victim(agent, world, params)
        if victim is None:
            return Err("nobody would believe me")
        return OK_NONE

    MALICE_FLOOR = 0.3
    """Below this, an agent simply is not the sort of person who does this."""

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Cunning and dishonest, and worth more when food is contested.

        Squared and floored on purpose. A linear score made nearly everyone
        a casual liar - 1,598 lies in five sim-days - because lying is free
        and most agents are mildly dishonest. Malice has to be a trait, not
        a mood.
        """
        if ctx.observation is not None and not ctx.observation.has_company:
            return 0.0
        malice = agent.traits.cunning * (1.0 - agent.traits.honesty)
        if malice < self.MALICE_FLOOR:
            return 0.0
        hunger = 1.0 - agent.needs.hunger / 100.0
        return 0.3 * malice * malice * (0.4 + hunger)

    def _victim(self, agent: Agent, world: World, params: BaseModel) -> Agent | None:
        """Someone nearby who does not already distrust us."""
        minds = self.services.minds
        candidates = (
            [world.agents.get(params.target)]
            if isinstance(params, TargetParams) and params.target is not None
            else nearby_agents(world, agent)
        )
        for other in candidates:
            if other is None or not other.alive:
                continue
            theirs = minds.require(other.id).memory.social.get(agent.id)
            if theirs is None or theirs.trust >= self.MIN_CREDULITY:
                return other
        return None

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Invent somewhere plausible and empty."""
        victim = self._victim(agent, world, params)
        stop(agent)
        rng = world.rngs["gossip"]
        angle = float(rng.uniform(0.0, 6.283185))
        distance = float(rng.uniform(self.LEAD_DISTANCE * 0.5, self.LEAD_DISTANCE))
        limit = world.terrain.half_size - 5.0
        target_x = max(-limit, min(limit, agent.position[0] + distance * float(np.cos(angle))))
        target_z = max(-limit, min(limit, agent.position[1] + distance * float(np.sin(angle))))

        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={
                "victim": -1 if victim is None else victim.id,
                "x": target_x,
                "z": target_z,
            },
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Plant the false lead in their head."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        if run.elapsed < GOSSIP_DURATION:
            return SkillStatus.RUNNING

        victim = world.agents.get(int(run.state["victim"]))
        if victim is None or not victim.alive:
            return SkillStatus.FAILED

        services = self.services
        where = (float(run.state["x"]), float(run.state["z"]))
        services.minds.require(victim.id).plant_false_lead(
            agent.id, where, world.clock.sim_seconds + self.LEAD_DURATION
        )
        services.ledger.lies_told += 1

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.LIE_TOLD,
                summary=f"{agent.name} sent {victim.name} chasing food that is not there",
                actors=(agent.id, victim.id),
                importance=6,
                position=agent.position,
            )
        )
        return SkillStatus.DONE


class Persuade(Skill):
    """Talk someone round. Charisma against stubbornness."""

    name = "Persuade"
    description = "Use charisma to improve how someone sees you."
    category = SkillCategory.MANIPULATION
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
