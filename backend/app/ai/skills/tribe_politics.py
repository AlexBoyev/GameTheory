"""Taking power inside a tribe: the coup (SPEC section 6).

Dealings *between* tribes live in `tribe_diplomacy`.
"""

from pydantic import BaseModel

from app.ai import social
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
from app.ai.skills.tribe import COUP_MARGIN, legitimacy
from app.core.result import OK_NONE, Err, Result
from app.sim.entities import Agent, AgentState, TribeRole
from app.sim.events import EventType, SimEvent
from app.sim.world import World


class ChallengeLeader(Skill):
    """Stage a coup, if the tribe trusts you more than it trusts the leader."""

    name = "ChallengeLeader"
    description = "Challenge your tribe's leader for the leadership."
    category = SkillCategory.TRIBE
    requires = frozenset({Requirement.IN_TRIBE})
    Params = NoParams
    visual_state = AgentState.SCHEME
    cooldown = 200.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a tribe, a leader who is not you, and some ambition."""
        if agent.tribe_id is None or agent.tribe_id not in world.tribes:
            return Err("not in a tribe")
        tribe = world.tribes[agent.tribe_id]
        if tribe.leader_id is None or tribe.leader_id == agent.id:
            return Err("already leading")
        if agent.traits.charisma < 0.45:
            return Err("not a plausible leader")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Ambition: charisma, low loyalty, and dislike of the incumbent."""
        if agent.tribe_id is None:
            return []
        tribe = ctx.world.tribes.get(agent.tribe_id)
        if tribe is None or tribe.leader_id in (None, agent.id):
            return []
        view = ctx.memory.social.get(tribe.leader_id) if tribe.leader_id else None
        resentment = max(0.0, -(view.trust if view else 0.0))
        ambition = agent.traits.charisma * (1.0 - agent.traits.loyalty)
        return [Consideration("ambitious and disloyal", ambition, 0.4 * (0.4 + resentment))]

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Make the challenge."""
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """The tribe decides by comparing legitimacy."""
        agent = world.agents[run.agent_id]
        tribe = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        if tribe is None or tribe.leader_id is None:
            return SkillStatus.FAILED
        leader = world.agents.get(tribe.leader_id)
        if leader is None or not leader.alive:
            tribe.leader_id = agent.id
            agent.role = TribeRole.LEADER
            return SkillStatus.DONE

        minds = self.services.minds
        mine = legitimacy(world, agent, tribe, minds)
        theirs = legitimacy(world, leader, tribe, minds)
        self.services.ledger.coup_attempts += 1
        if mine <= theirs + COUP_MARGIN:
            # A failed coup is remembered.
            relationship = minds.require(leader.id).memory.relationship(agent.id)
            social.adjust_trust(relationship, -0.45)
            world.events.emit(
                SimEvent(
                    tick=world.clock.tick,
                    type=EventType.COUP,
                    summary=f"{agent.name} challenged {leader.name} and lost",
                    actors=(agent.id, leader.id),
                    importance=7,
                    position=agent.position,
                    data={"tribe": tribe.id, "succeeded": False},
                )
            )
            return SkillStatus.FAILED

        tribe.leader_id = agent.id
        agent.role = TribeRole.LEADER
        leader.role = TribeRole.ELDER
        self.services.ledger.coups += 1
        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.COUP,
                summary=f"{agent.name} overthrew {leader.name} to lead {tribe.name}",
                actors=(agent.id, leader.id),
                importance=9,
                position=agent.position,
                data={"tribe": tribe.id, "succeeded": True},
            )
        )
        return SkillStatus.DONE
