"""Spreading things that are not true (SPEC section 6).

Gossip carries a belief about a third party, true or false; Lie plants a false
lead about where food is. The point is that information is neither free nor
reliable: an agent's reputation is whatever the last person to mention them
said, weighted by how much the listener trusted the teller - so a charismatic
liar can destroy someone they have never met, and get away with it until the
evidence piles up.
"""

import numpy as np
from pydantic import BaseModel, ConfigDict

from app.ai import social
from app.ai.brains.base import DecisionContext
from app.ai.skills.base import Requirement, Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import stop
from app.ai.skills.manipulation import GOSSIP_DURATION, KNOWS_BETTER_TRUST
from app.ai.skills.targeting import TargetParams, nearby_agents, resolve_target
from app.core.result import OK_NONE, Err, Result
from app.sim.entities import Agent, AgentState
from app.sim.events import EventType, SimEvent
from app.sim.world import World


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
    requires = frozenset({Requirement.NEARBY_AGENTS})
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
    requires = frozenset({Requirement.NEARBY_AGENTS})
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
