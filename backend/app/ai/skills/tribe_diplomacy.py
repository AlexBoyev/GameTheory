"""Dealings between tribes: war, peace and pacts (SPEC section 6).

Taking power *inside* a tribe is `tribe_politics`. Every skill here is for
leaders only, and each one writes to both tribes, never just the actor's.
"""

from pydantic import BaseModel, ConfigDict

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
from app.ai.skills.helpers import stop
from app.core.result import OK_NONE, Err, Result
from app.sim.entities import Agent, AgentState, TribeRole
from app.sim.events import EventType, SimEvent
from app.sim.world import World


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

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Aggressive leaders with a disliked neighbour."""
        if agent.role is not TribeRole.LEADER:
            return []
        return [
            Consideration(
                "aggressive",
                agent.traits.aggression,
                0.3 * (1.0 - agent.traits.honesty + 0.3),
            )
        ]

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

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Peaceable leaders, and anyone whose tribe is losing people.

        The original product expands exactly into these two, and the war
        weariness deserves its own name in the trace.
        """
        if agent.role is not TribeRole.LEADER or agent.tribe_id is None:
            return []
        tribe = ctx.world.tribes.get(agent.tribe_id)
        if tribe is None or not tribe.at_war_with:
            return []
        weakness = 1.0 - min(1.0, tribe.size / 8.0)
        peaceable = 1.0 - agent.traits.aggression
        return [
            Consideration("peaceable", peaceable, 0.35 * 0.4),
            Consideration("the tribe is losing people", weakness, 0.35 * peaceable),
        ]

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


class OfferAlliance(Skill):
    """Offer a formal pact to a tribe your people like.

    The counterpart of agent-level `ProposeAlliance`, and the only way
    `Tribe.allied_with` is ever written to. It went missing for a while: the
    field, its DTO, its serialisation and `DeclareWar`'s pact-breaking were
    all in place, and nothing could form a pact in the first instance.
    """

    name = "OfferAlliance"
    description = "Offer a formal alliance to a friendly tribe."
    category = SkillCategory.TRIBE
    requires = frozenset({Requirement.TRIBE_LEADER})
    Params = TribeTargetParams
    visual_state = AgentState.TALK
    cooldown = 300.0

    WARMTH_REQUIRED = 0.15
    """Average opinion of their members below which a pact is not worth asking for."""

    REFUSES_ABOVE = 0.8
    """A leader this aggressive would rather keep their hands free."""

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Only a leader, and only towards a tribe we are warm about."""
        if agent.role is not TribeRole.LEADER or agent.tribe_id is None:
            return Err("only a leader may offer an alliance")
        if self._friend(agent, world) is None:
            return Err("no tribe worth a pact")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Sociable leaders seek pacts, and small tribes need them most."""
        if agent.role is not TribeRole.LEADER or agent.tribe_id is None:
            return []
        tribe = ctx.world.tribes.get(agent.tribe_id)
        if tribe is None:
            return []
        weakness = 1.0 - min(1.0, tribe.size / 8.0)
        return [
            Consideration("sociable", agent.traits.sociability, 0.3 * (0.4 + agent.traits.loyalty)),
            Consideration("safety in numbers", weakness, 0.3),
        ]

    def _friend(self, agent: Agent, world: World) -> int | None:
        """The tribe whose members we think best of, if we think well enough.

        The mirror of `DeclareWar._enemy`: same averaging, opposite sign, and
        the same exclusions - ourselves, anyone we are fighting, and anyone we
        have already signed with.
        """
        own = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        if own is None:
            return None
        memory = self.services.minds.require(agent.id).memory
        best: int | None = None
        warmest = self.WARMTH_REQUIRED
        for tribe_id, tribe in sorted(world.tribes.items()):
            if tribe_id == own.id or tribe_id in own.at_war_with or tribe_id in own.allied_with:
                continue
            opinions = [
                social.effective_opinion(memory, member_id) for member_id in tribe.member_ids
            ]
            if not opinions:
                continue
            average = sum(opinions) / len(opinions)
            if average > warmest:
                warmest, best = average, tribe_id
        return best

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Name the tribe being courted."""
        friend = self._friend(agent, world)
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"friend": -1 if friend is None else friend},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """The pact holds unless their leader prefers a free hand."""
        agent = world.agents[run.agent_id]
        own = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        friend = world.tribes.get(int(run.state["friend"]))
        if own is None or friend is None or friend.id in own.at_war_with:
            return SkillStatus.FAILED

        their_leader = world.agents.get(friend.leader_id) if friend.leader_id else None
        if their_leader is not None and their_leader.traits.aggression > self.REFUSES_ABOVE:
            return SkillStatus.FAILED

        own.allied_with.add(friend.id)
        friend.allied_with.add(own.id)
        self.services.ledger.alliances += 1

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.ALLIANCE,
                summary=f"{own.name} and {friend.name} signed a pact",
                actors=(agent.id,),
                importance=8,
                position=agent.position,
                data={"tribe": own.id, "with": friend.id},
            )
        )
        return SkillStatus.DONE
