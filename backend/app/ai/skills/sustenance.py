"""Staying alive: Gather, Eat, Drink, Sleep (SPEC section 7.3)."""

from pydantic import BaseModel, ConfigDict

from app.ai.brains.base import DecisionContext
from app.ai.skills.base import NoParams, Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import nearest_resource, need_urgency, steer_towards, stop
from app.core.result import OK_NONE, Err, Result
from app.sim import balance
from app.sim.entities import Agent, AgentState, ResourceKind
from app.sim.world import World

EDIBLE: frozenset[ResourceKind] = frozenset({ResourceKind.BERRY_BUSH, ResourceKind.CORPSE})
"""What `Gather` will pick up. Wood and stone wait for BuildShelter."""

WATER: frozenset[ResourceKind] = frozenset({ResourceKind.WATER})

FULL_ENOUGH = 95.0
HYDRATED_ENOUGH = 99.0
RESTED_ENOUGH = 99.0
SLEEPY_BELOW = 85.0
NIGHT_SLEEP_BONUS = 0.45


class GatherParams(BaseModel):
    """Which node to harvest; defaults to the nearest edible one."""

    model_config = ConfigDict(extra="forbid")

    resource_id: int | None = None


def _resolve_node_id(agent: Agent, world: World, params: BaseModel) -> int | None:
    """Return the requested node id, or the nearest edible node's id."""
    if isinstance(params, GatherParams) and params.resource_id is not None:
        node = world.resources.get(params.resource_id)
        return node.id if node is not None and not node.depleted else None
    node = nearest_resource(world, agent, EDIBLE)
    return node.id if node is not None else None


class Gather(Skill):
    """Walk to food and pick it up until carrying enough."""

    name = "Gather"
    description = "Harvest berries (or a carcass) into your inventory."
    category = SkillCategory.SURVIVAL
    Params = GatherParams
    visual_state = AgentState.GATHER

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require room to carry more and something in range to pick."""
        if agent.inventory.food >= balance.CARRY_TARGET:
            return Err("already carrying enough food")
        if _resolve_node_id(agent, world, params) is None:
            return Err("no food in sight")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Want food when hungry, or when the larder is empty and greed says so."""
        hunger = need_urgency(agent.needs.hunger)
        stock = min(1.0, agent.inventory.food / balance.CARRY_TARGET)
        return 0.6 * hunger + 0.3 * (1.0 - stock) * (0.4 + agent.traits.greed)

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Lock on to a node and start walking."""
        node_id = _resolve_node_id(agent, world, params)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"node": -1 if node_id is None else node_id, "arrived": False, "taken": 0.0},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Walk there, then harvest until full or the node is empty."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        node = world.resources.get(int(run.state["node"]))

        if node is None or node.depleted:
            stop(agent)
            return SkillStatus.DONE if run.state["taken"] else SkillStatus.FAILED

        if not run.state["arrived"]:
            if not steer_towards(agent, node.position):
                return SkillStatus.RUNNING
            run.state["arrived"] = True

        room = balance.CARRY_TARGET - agent.inventory.food
        take = min(balance.GATHER_RATE * dt, node.amount, room)
        node.amount -= take
        agent.inventory.food += take
        run.state["taken"] = float(run.state["taken"]) + take

        if agent.inventory.food >= balance.CARRY_TARGET or node.depleted:
            stop(agent)
            return SkillStatus.DONE
        return SkillStatus.RUNNING


class Eat(Skill):
    """Eat one unit of carried food."""

    name = "Eat"
    description = "Eat food you are carrying."
    category = SkillCategory.SURVIVAL
    Params = NoParams
    visual_state = AgentState.EAT

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require carried food and some room for it."""
        if agent.inventory.food <= 0.0:
            return Err("nothing to eat")
        if agent.needs.hunger >= FULL_ENOUGH:
            return Err("not hungry")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Eating beats fetching: it is the fastest fix for hunger."""
        if agent.inventory.food <= 0.0:
            return 0.0
        return need_urgency(agent.needs.hunger) * 1.25

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Take one unit out of the inventory up front."""
        portion = min(1.0, agent.inventory.food)
        agent.inventory.food -= portion
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"portion": portion},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Convert the portion into hunger relief over `EAT_DURATION`."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        gain = balance.EAT_PER_FOOD * float(run.state["portion"]) / balance.EAT_DURATION
        agent.needs.hunger = min(balance.NEED_MAX, agent.needs.hunger + gain * dt)
        return SkillStatus.DONE if run.elapsed >= balance.EAT_DURATION else SkillStatus.RUNNING


class Drink(Skill):
    """Walk to water and drink."""

    name = "Drink"
    description = "Walk to the shore or a lake and drink."
    category = SkillCategory.SURVIVAL
    Params = NoParams
    visual_state = AgentState.DRINK

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require thirst and water within sight."""
        if agent.needs.thirst >= HYDRATED_ENOUGH:
            return Err("not thirsty")
        if nearest_resource(world, agent, WATER, balance.LANDMARK_RADIUS) is None:
            return Err("no water in sight")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Thirst kills faster than hunger, so it scores higher."""
        return need_urgency(agent.needs.thirst) * 1.4

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Head for the nearest water."""
        node = nearest_resource(world, agent, WATER, balance.LANDMARK_RADIUS)
        target = node.position if node is not None else agent.position
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"x": target[0], "z": target[1], "arrived": node is None},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Walk to the water's edge, then drink until satisfied."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt

        if not run.state["arrived"]:
            target = (float(run.state["x"]), float(run.state["z"]))
            if not steer_towards(agent, target):
                return SkillStatus.RUNNING
            run.state["arrived"] = True

        agent.needs.thirst = min(balance.NEED_MAX, agent.needs.thirst + balance.DRINK_RATE * dt)
        if agent.needs.thirst >= HYDRATED_ENOUGH:
            stop(agent)
            return SkillStatus.DONE
        return SkillStatus.RUNNING


class Sleep(Skill):
    """Lie down and recover energy."""

    name = "Sleep"
    description = "Sleep to recover energy."
    category = SkillCategory.SURVIVAL
    Params = NoParams
    visual_state = AgentState.SLEEP

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require being at least a little tired."""
        if agent.needs.energy >= SLEEPY_BELOW:
            return Err("not tired")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Sleep at night, or whenever exhaustion starts doing damage."""
        tiredness = need_urgency(agent.needs.energy)
        night_bonus = NIGHT_SLEEP_BONUS if world_is_night(ctx) else 0.0
        return tiredness * (0.8 + night_bonus)

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Stop moving."""
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Recover energy until rested."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        agent.needs.energy = min(balance.NEED_MAX, agent.needs.energy + balance.SLEEP_RATE * dt)
        return SkillStatus.DONE if agent.needs.energy >= RESTED_ENOUGH else SkillStatus.RUNNING


def world_is_night(ctx: DecisionContext) -> bool:
    """Return whether it is night, from the observation or the world clock."""
    if ctx.observation is not None:
        return ctx.observation.is_night
    return ctx.world.clock.is_night
