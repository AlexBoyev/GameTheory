"""Founding, joining and leaving a tribe (SPEC section 6)."""

from pydantic import BaseModel

from app.ai.brains.base import DecisionContext
from app.ai.skills.base import (
    Consideration,
    NoParams,
    Requirement,
    Skill,
    SkillCategory,
    SkillRun,
    SkillStatus,
)
from app.ai.skills.helpers import stop
from app.ai.skills.targeting import TargetParams, nearby_agents
from app.ai.skills.tribe import FOUND_ALLIES, FOUND_CHARISMA, JOIN_TRUST
from app.core.result import OK_NONE, Err, Result
from app.sim import balance
from app.sim.entities import Agent, AgentState, Tribe, TribeRole
from app.sim.events import EventType, SimEvent
from app.sim.tribe_identity import TRIBE_COLOURS, tribe_name
from app.sim.world import World


class FoundTribe(Skill):
    """Declare a tribe and become its first leader."""

    name = "FoundTribe"
    description = "Found a new tribe with the people who trust you."
    category = SkillCategory.TRIBE
    requires = frozenset({Requirement.TRIBELESS})
    Params = NoParams
    visual_state = AgentState.TALK
    cooldown = 300.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require charisma, no tribe already, and at least one follower."""
        if agent.tribe_id is not None:
            return Err("already in a tribe")
        if agent.traits.charisma < FOUND_CHARISMA:
            return Err("nobody would follow me")
        if len(world.tribes) >= 16:
            return Err("the island has enough tribes")
        if len(self._followers(agent, world)) < FOUND_ALLIES:
            return Err("no willing followers nearby")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Charismatic agents with friends around them start things."""
        if agent.tribe_id is not None or agent.traits.charisma < FOUND_CHARISMA:
            return []
        friends = sum(
            1
            for other_id, relationship in ctx.memory.social.items()
            if relationship.trust >= JOIN_TRUST
            and (ctx.observation is None or other_id in ctx.observation.visible_agents)
        )
        if friends < FOUND_ALLIES:
            return []
        return [
            Consideration(
                "friends willing to follow",
                min(1.0, friends / 3.0),
                0.4 * agent.traits.charisma,
            )
        ]

    def _followers(self, agent: Agent, world: World) -> list[Agent]:
        """Nearby tribeless agents who trust us enough to follow."""
        minds = self.services.minds
        followers: list[Agent] = []
        for other in nearby_agents(world, agent, radius=balance.VISION_RADIUS):
            if other.tribe_id is not None:
                continue
            theirs = minds.require(other.id).memory.social.get(agent.id)
            if theirs is not None and theirs.trust >= JOIN_TRUST:
                followers.append(other)
        return followers

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Gather the willing."""
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Create the tribe and enrol whoever was willing."""
        agent = world.agents[run.agent_id]
        if agent.tribe_id is not None:
            return SkillStatus.FAILED
        followers = self._followers(agent, world)
        if not followers:
            return SkillStatus.FAILED

        tribe = Tribe(
            id=world.next_tribe_id,
            name=tribe_name(world.next_tribe_id),
            colour=TRIBE_COLOURS[world.next_tribe_id % len(TRIBE_COLOURS)],
            leader_id=agent.id,
            camp_position=agent.position,
            territory_radius=18.0,
            founded_tick=world.clock.tick,
        )
        world.tribes[tribe.id] = tribe
        world.next_tribe_id += 1

        for member in (agent, *followers):
            member.tribe_id = tribe.id
            member.role = TribeRole.LEADER if member is agent else TribeRole.MEMBER
            tribe.member_ids.add(member.id)

        self.services.ledger.tribes_founded += 1
        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.TRIBE_FOUNDED,
                summary=f"{agent.name} founded {tribe.name} with {len(followers)} followers",
                actors=(agent.id,),
                importance=9,
                position=agent.position,
                data={"tribe": tribe.id, "size": tribe.size},
            )
        )
        return SkillStatus.DONE


class JoinTribe(Skill):
    """Join a tribe whose members you trust."""

    name = "JoinTribe"
    description = "Join a nearby tribe."
    category = SkillCategory.TRIBE
    requires = frozenset({Requirement.TRIBELESS, Requirement.NEARBY_AGENTS})
    Params = TargetParams
    visual_state = AgentState.TALK
    cooldown = 60.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require no tribe, and a tribe member nearby who you trust."""
        if agent.tribe_id is not None:
            return Err("already in a tribe")
        if self._host(agent, world) is None:
            return Err("no tribe worth joining nearby")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Loyal, sociable, unsafe agents want to belong.

        The original single product expands exactly into these two inputs,
        which is the better reading: a standing wish to belong, plus however
        unsafe the agent currently feels.
        """
        if agent.tribe_id is not None:
            return []
        safety_pull = 1.0 - agent.needs.safety / balance.NEED_MAX
        sociable = 0.35 * (0.4 + agent.traits.loyalty)
        return [
            Consideration("wants to belong", 1.0, sociable * 0.3),
            Consideration("feels unsafe alone", safety_pull, sociable),
        ]

    def _host(self, agent: Agent, world: World) -> Agent | None:
        """A nearby tribe member we trust and who tolerates us."""
        memory = self.services.minds.require(agent.id).memory
        for other in nearby_agents(world, agent, radius=balance.VISION_RADIUS):
            if other.tribe_id is None or other.tribe_id not in world.tribes:
                continue
            ours = memory.social.get(other.id)
            if ours is not None and ours.trust >= JOIN_TRUST:
                return other
        return None

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Approach the tribe."""
        host = self._host(agent, world)
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"host": -1 if host is None else host.id},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Enrol."""
        agent = world.agents[run.agent_id]
        host = world.agents.get(int(run.state["host"]))
        if host is None or host.tribe_id is None:
            return SkillStatus.FAILED
        tribe = world.tribes.get(host.tribe_id)
        if tribe is None:
            return SkillStatus.FAILED

        agent.tribe_id = tribe.id
        agent.role = TribeRole.MEMBER
        tribe.member_ids.add(agent.id)

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.TRIBE_JOINED,
                summary=f"{agent.name} joined {tribe.name}",
                actors=(agent.id,),
                importance=5,
                position=agent.position,
                data={"tribe": tribe.id},
            )
        )
        return SkillStatus.DONE


class LeaveTribe(Skill):
    """Walk away from a tribe you no longer trust."""

    name = "LeaveTribe"
    description = "Leave your tribe."
    category = SkillCategory.TRIBE
    requires = frozenset({Requirement.IN_TRIBE})
    Params = NoParams
    visual_state = AgentState.WANDER
    cooldown = 120.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a tribe to leave."""
        if agent.tribe_id is None:
            return Err("not in a tribe")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Leaving is for the disillusioned: low trust in your own leader."""
        if agent.tribe_id is None:
            return []
        tribe = ctx.world.tribes.get(agent.tribe_id)
        if tribe is None or tribe.leader_id is None or tribe.leader_id == agent.id:
            return []
        relationship = ctx.memory.social.get(tribe.leader_id)
        if relationship is None or relationship.trust > -0.2:
            return []
        return [
            Consideration(
                "lost faith in the leader",
                -relationship.trust,
                0.4 * (1.0 - agent.traits.loyalty),
            )
        ]

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Pack up."""
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Leave, and stop being the leader if you were."""
        agent = world.agents[run.agent_id]
        tribe = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        if tribe is None:
            agent.tribe_id = None
            agent.role = TribeRole.NONE
            return SkillStatus.DONE

        tribe.member_ids.discard(agent.id)
        if tribe.leader_id == agent.id:
            tribe.leader_id = next(iter(sorted(tribe.member_ids)), None)
        agent.tribe_id = None
        agent.role = TribeRole.NONE

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.TRIBE_LEFT,
                summary=f"{agent.name} left {tribe.name}",
                actors=(agent.id,),
                importance=5,
                position=agent.position,
                data={"tribe": tribe.id},
            )
        )
        return SkillStatus.DONE
