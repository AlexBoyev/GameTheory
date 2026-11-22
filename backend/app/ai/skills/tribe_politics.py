"""Taking power, declaring war, and suing for peace (SPEC section 6)."""

from pydantic import BaseModel, ConfigDict

from app.ai import social
from app.ai.brains.base import DecisionContext
from app.ai.skills.base import NoParams, Requirement, Skill, SkillCategory, SkillRun, SkillStatus
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

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Ambition: charisma, low loyalty, and dislike of the incumbent."""
        if agent.tribe_id is None:
            return 0.0
        tribe = ctx.world.tribes.get(agent.tribe_id)
        if tribe is None or tribe.leader_id in (None, agent.id):
            return 0.0
        view = ctx.memory.social.get(tribe.leader_id) if tribe.leader_id else None
        resentment = max(0.0, -(view.trust if view else 0.0))
        return 0.4 * agent.traits.charisma * (1.0 - agent.traits.loyalty) * (0.4 + resentment)

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


class TribeTargetParams(BaseModel):
    """Which other tribe this concerns."""

    model_config = ConfigDict(extra="forbid")

    tribe: int | None = None


class DeclareWar(Skill):
    """Declare war on a tribe your people distrust."""

    name = "DeclareWar"
    description = "Declare war on a rival tribe."
    category = SkillCategory.TRIBE
    requires = frozenset({Requirement.TRIBE_LEADER})
    Params = TribeTargetParams
    visual_state = AgentState.SCHEME
    cooldown = 400.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Only a leader can declare war, and only on someone else."""
        if agent.role is not TribeRole.LEADER or agent.tribe_id is None:
            return Err("only a leader may declare war")
        if self._enemy(agent, world) is None:
            return Err("no rival worth a war")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Aggressive leaders with a disliked neighbour."""
        if agent.role is not TribeRole.LEADER:
            return 0.0
        return 0.3 * agent.traits.aggression * (1.0 - agent.traits.honesty + 0.3)

    def _enemy(self, agent: Agent, world: World) -> int | None:
        """The nearest tribe we are not already fighting."""
        own = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        if own is None:
            return None
        memory = self.services.minds.require(agent.id).memory
        worst: int | None = None
        lowest = -0.15
        for tribe_id, tribe in sorted(world.tribes.items()):
            if tribe_id == own.id or tribe_id in own.at_war_with:
                continue
            opinions = [
                social.effective_opinion(memory, member_id) for member_id in tribe.member_ids
            ]
            if not opinions:
                continue
            average = sum(opinions) / len(opinions)
            if average < lowest:
                lowest, worst = average, tribe_id
        return worst

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Name the enemy."""
        enemy = self._enemy(agent, world)
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"enemy": -1 if enemy is None else enemy},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Set both tribes at war."""
        agent = world.agents[run.agent_id]
        own = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        enemy = world.tribes.get(int(run.state["enemy"]))
        if own is None or enemy is None:
            return SkillStatus.FAILED

        own.at_war_with.add(enemy.id)
        enemy.at_war_with.add(own.id)
        own.allied_with.discard(enemy.id)
        enemy.allied_with.discard(own.id)
        self.services.ledger.wars_declared += 1

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.WAR_DECLARED,
                summary=f"{own.name} declared war on {enemy.name}",
                actors=(agent.id,),
                importance=10,
                position=agent.position,
                data={"tribe": own.id, "enemy": enemy.id},
            )
        )
        return SkillStatus.DONE


class OfferPeace(Skill):
    """Sue for peace."""

    name = "OfferPeace"
    description = "Offer peace to a tribe you are at war with."
    category = SkillCategory.TRIBE
    requires = frozenset({Requirement.TRIBE_LEADER})
    Params = TribeTargetParams
    visual_state = AgentState.TALK
    cooldown = 200.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Only a leader at war can make peace."""
        if agent.role is not TribeRole.LEADER or agent.tribe_id is None:
            return Err("only a leader may offer peace")
        own = world.tribes.get(agent.tribe_id)
        if own is None or not own.at_war_with:
            return Err("not at war")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Peaceable leaders, and anyone whose tribe is losing people."""
        if agent.role is not TribeRole.LEADER or agent.tribe_id is None:
            return 0.0
        tribe = ctx.world.tribes.get(agent.tribe_id)
        if tribe is None or not tribe.at_war_with:
            return 0.0
        weakness = 1.0 - min(1.0, tribe.size / 8.0)
        return 0.35 * (1.0 - agent.traits.aggression) * (0.4 + weakness)

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Send the offer."""
        own = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        enemy = next(iter(sorted(own.at_war_with)), -1) if own else -1
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"enemy": enemy},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Peace holds if the other leader is not spoiling for a fight."""
        agent = world.agents[run.agent_id]
        own = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        enemy = world.tribes.get(int(run.state["enemy"]))
        if own is None or enemy is None:
            return SkillStatus.FAILED

        enemy_leader = world.agents.get(enemy.leader_id) if enemy.leader_id else None
        if enemy_leader is not None and enemy_leader.traits.aggression > 0.75:
            return SkillStatus.FAILED

        own.at_war_with.discard(enemy.id)
        enemy.at_war_with.discard(own.id)
        self.services.ledger.peace_made += 1

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.PEACE_MADE,
                summary=f"{own.name} and {enemy.name} made peace",
                actors=(agent.id,),
                importance=9,
                position=agent.position,
                data={"tribe": own.id, "with": enemy.id},
            )
        )
        return SkillStatus.DONE
