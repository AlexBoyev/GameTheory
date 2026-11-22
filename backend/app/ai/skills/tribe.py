"""Tribes: founding, joining, storage, coups and diplomacy (SPEC section 6).

A tribe here is not a label an agent is assigned - it is a thing somebody
*founds*, that others choose to join because they trust the founder, that
feeds its members from a shared store, and that can be taken over by anyone
the members trust more than the current leader.
"""

from pydantic import BaseModel, ConfigDict

from app.ai import social
from app.ai.brains.base import DecisionContext
from app.ai.minds import MindRegistry
from app.ai.skills.base import NoParams, Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import stop
from app.ai.skills.social import TargetParams, nearby_agents
from app.core.result import OK_NONE, Err, Result
from app.sim import balance
from app.sim.entities import Agent, AgentState, Tribe, TribeRole
from app.sim.events import EventType, SimEvent
from app.sim.tribe_identity import TRIBE_COLOURS, tribe_name
from app.sim.world import World

FOUND_CHARISMA = 0.55
FOUND_ALLIES = 1
JOIN_TRUST = 0.3
STORE_AMOUNT = 2.0
TAKE_AMOUNT = 2.0
COUP_MARGIN = 0.25


def legitimacy(world: World, agent: Agent, tribe: Tribe, minds: MindRegistry) -> float:
    """Reputation x charisma x tenure - who the tribe would follow (SPEC 6).

    "Reputation" here is literally what the members think: the average trust
    the tribe holds in this agent. A leader nobody likes is not legitimate,
    however charismatic.
    """
    standing = 0.0
    counted = 0
    for member_id in sorted(tribe.member_ids):
        if member_id == agent.id or member_id not in world.agents:
            continue
        relationship = minds.require(member_id).memory.social.get(agent.id)
        if relationship is not None:
            standing += relationship.trust
            counted += 1
    average = standing / counted if counted else 0.0
    tenure = min(1.0, (world.clock.tick - tribe.founded_tick) / 6000.0)
    return (0.5 + 0.5 * average) * (0.4 + 0.6 * agent.traits.charisma) * (0.7 + 0.3 * tenure)


class FoundTribe(Skill):
    """Declare a tribe and become its first leader."""

    name = "FoundTribe"
    description = "Found a new tribe with the people who trust you."
    category = SkillCategory.TRIBE
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

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Charismatic agents with friends around them start things."""
        if agent.tribe_id is not None or agent.traits.charisma < FOUND_CHARISMA:
            return 0.0
        friends = sum(
            1
            for other_id, relationship in ctx.memory.social.items()
            if relationship.trust >= JOIN_TRUST
            and (ctx.observation is None or other_id in ctx.observation.visible_agents)
        )
        if friends < FOUND_ALLIES:
            return 0.0
        return 0.4 * agent.traits.charisma * min(1.0, friends / 3.0)

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

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Loyal, sociable, unsafe agents want to belong."""
        if agent.tribe_id is not None:
            return 0.0
        safety_pull = 1.0 - agent.needs.safety / balance.NEED_MAX
        return 0.35 * (0.4 + agent.traits.loyalty) * (0.3 + safety_pull)

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
    Params = NoParams
    visual_state = AgentState.WANDER
    cooldown = 120.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a tribe to leave."""
        if agent.tribe_id is None:
            return Err("not in a tribe")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Leaving is for the disillusioned: low trust in your own leader."""
        if agent.tribe_id is None:
            return 0.0
        tribe = ctx.world.tribes.get(agent.tribe_id)
        if tribe is None or tribe.leader_id is None or tribe.leader_id == agent.id:
            return 0.0
        relationship = ctx.memory.social.get(tribe.leader_id)
        if relationship is None or relationship.trust > -0.2:
            return 0.0
        return 0.4 * (-relationship.trust) * (1.0 - agent.traits.loyalty)

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


class StoreFood(Skill):
    """Put food into the tribe's common store - the Public Goods game."""

    name = "StoreFood"
    description = "Contribute food to your tribe's store."
    category = SkillCategory.TRIBE
    Params = NoParams
    visual_state = AgentState.TRADE
    cooldown = 30.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a tribe and spare food."""
        if agent.tribe_id is None or agent.tribe_id not in world.tribes:
            return Err("no tribe to give to")
        if agent.inventory.food < STORE_AMOUNT + 1.0:
            return Err("nothing to spare")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Loyalty against greed: this is the free-rider decision."""
        if agent.tribe_id is None or agent.inventory.food < STORE_AMOUNT + 1.0:
            return 0.0
        public_spirit = agent.traits.loyalty * (1.0 - agent.traits.greed)
        return 0.4 * public_spirit

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Walk it over."""
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Contribute, and be thought better of for it."""
        agent = world.agents[run.agent_id]
        tribe = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        if tribe is None or agent.inventory.food < STORE_AMOUNT:
            return SkillStatus.FAILED

        agent.inventory.food -= STORE_AMOUNT
        tribe.storage_food += STORE_AMOUNT

        minds = self.services.minds
        for member_id in sorted(tribe.member_ids):
            if member_id == agent.id or member_id not in world.agents:
                continue
            social.adjust_trust(minds.require(member_id).memory.relationship(agent.id), 0.05)
        return SkillStatus.DONE


class TakeFromStorage(Skill):
    """Draw on the common store when hungry - or when greedy."""

    name = "TakeFromStorage"
    description = "Take food from your tribe's store."
    category = SkillCategory.TRIBE
    Params = NoParams
    visual_state = AgentState.TRADE
    cooldown = 25.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a tribe with something in the store, and an appetite."""
        if agent.tribe_id is None or agent.tribe_id not in world.tribes:
            return Err("no tribe store")
        if world.tribes[agent.tribe_id].storage_food < TAKE_AMOUNT:
            return Err("the store is empty")
        if agent.needs.hunger > 70.0 and agent.inventory.food > 1.0:
            return Err("not hungry enough to need it")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Hunger drives it; greed makes an agent reach sooner."""
        if agent.tribe_id is None:
            return 0.0
        hunger = 1.0 - agent.needs.hunger / balance.NEED_MAX
        return 0.5 * hunger * (0.6 + 0.4 * agent.traits.greed)

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Go to the store."""
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Take a share. Taking without giving is noticed over time."""
        agent = world.agents[run.agent_id]
        tribe = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        if tribe is None or tribe.storage_food < TAKE_AMOUNT:
            return SkillStatus.FAILED

        tribe.storage_food -= TAKE_AMOUNT
        agent.inventory.food += TAKE_AMOUNT
        return SkillStatus.DONE


class ChallengeLeader(Skill):
    """Stage a coup, if the tribe trusts you more than it trusts the leader."""

    name = "ChallengeLeader"
    description = "Challenge your tribe's leader for the leadership."
    category = SkillCategory.TRIBE
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
