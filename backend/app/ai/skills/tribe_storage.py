"""The common store: the public-goods game, as a pair of skills (SPEC 6)."""

from pydantic import BaseModel

from app.ai import social
from app.ai.brains.base import DecisionContext
from app.ai.skills.base import NoParams, Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import stop
from app.ai.skills.tribe import STORE_AMOUNT, TAKE_AMOUNT
from app.core.result import OK_NONE, Err, Result
from app.sim import balance
from app.sim.entities import Agent, AgentState
from app.sim.world import World


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
