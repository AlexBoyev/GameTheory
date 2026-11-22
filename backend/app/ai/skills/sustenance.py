"""Staying alive: Gather, Eat, Drink, Sleep (SPEC section 7.3)."""

from pydantic import BaseModel, ConfigDict

from app.ai import social
from app.ai.brains.base import DecisionContext
from app.ai.skills.base import Consideration, NoParams, Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import nearest_resource, need_urgency, steer_towards, stop
from app.core.result import OK_NONE, Err, Result
from app.sim import balance
from app.sim.entities import Agent, AgentState, ResourceKind, Shelter
from app.sim.events import EventType, SimEvent
from app.sim.world import World

EDIBLE: frozenset[ResourceKind] = frozenset({ResourceKind.BERRY_BUSH, ResourceKind.CORPSE})
"""What `Gather` will pick up. Wood and stone wait for BuildShelter."""

WATER: frozenset[ResourceKind] = frozenset({ResourceKind.WATER})

FULL_ENOUGH = 95.0
HYDRATED_ENOUGH = 99.0
RESTED_ENOUGH = 99.0
SLEEPY_BELOW = 85.0
NIGHT_SLEEP_BONUS = 0.45

SHELTER_COMFORT_RADIUS = 4.0
SHELTER_REST_BONUS = 0.8
"""A good hut makes sleep most of twice as fast - the point of building one."""


def shelter_near(world: World, position: tuple[float, float], radius: float) -> Shelter | None:
    """Return a shelter within `radius` of `position`, if there is one."""
    best: Shelter | None = None
    best_distance = radius * radius
    for shelter_id in sorted(world.shelters):
        shelter = world.shelters[shelter_id]
        distance = (shelter.position[0] - position[0]) ** 2 + (
            shelter.position[1] - position[1]
        ) ** 2
        if distance <= best_distance:
            best_distance, best = distance, shelter
    return best


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

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Want food when hungry, or when the larder is empty and greed says so."""
        stock = min(1.0, agent.inventory.food / balance.CARRY_TARGET)
        return [
            Consideration("hungry", need_urgency(agent.needs.hunger), 0.6),
            # The value stays in [0, 1] and the magnitude goes in the weight:
            # `apply_curve` clamps the value, so a greedy agent's 1.4 would
            # quietly become 1.0.
            Consideration("larder empty", 1.0 - stock, 0.3 * (0.4 + agent.traits.greed)),
        ]

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Lock on to a node - unless someone has lied about where food is."""
        mind = self.services.minds.require(agent.id)
        lead = mind.take_false_lead(world.clock.sim_seconds)
        if lead is not None:
            return SkillRun(
                skill=self.name,
                agent_id=agent.id,
                params=params,
                started_tick=world.clock.tick,
                state={"node": -1, "arrived": False, "taken": 0.0, "lx": lead[0], "lz": lead[1]},
            )

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

        if "lx" in run.state:
            return self._chase_false_lead(run, world, agent)

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

    def _chase_false_lead(self, run: SkillRun, world: World, agent: Agent) -> SkillStatus:
        """Walk to where you were told food was, and find bare ground.

        The wasted journey *is* the damage. Working out who sent you is a
        second, separate thing - and not everyone does.
        """
        target = (float(run.state["lx"]), float(run.state["lz"]))
        if not steer_towards(agent, target):
            return SkillStatus.RUNNING

        stop(agent)
        mind = self.services.minds.require(agent.id)
        liar_id = mind.clear_false_lead()
        if liar_id is None:
            return SkillStatus.FAILED

        liar = world.agents.get(liar_id)
        if liar is None:
            return SkillStatus.FAILED

        # Standing on empty ground, do they realise they were played?
        chance = social.lie_detection_chance(liar.traits, agent.traits, listener_knows_better=True)
        if float(world.rngs["gossip"].random()) >= chance:
            return SkillStatus.FAILED

        social.punish_caught_liar(mind.memory, liar_id)
        self.services.ledger.lies_caught += 1
        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.LIE_CAUGHT,
                summary=f"{agent.name} realised {liar.name} had lied about the food",
                actors=(agent.id, liar_id),
                importance=7,
                position=agent.position,
            )
        )
        return SkillStatus.FAILED


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

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Eating beats fetching: it is the fastest fix for hunger."""
        if agent.inventory.food <= 0.0:
            return []
        return [Consideration("hungry", need_urgency(agent.needs.hunger), 1.25)]

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

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Thirst kills faster than hunger, so it scores higher."""
        return [Consideration("thirsty", need_urgency(agent.needs.thirst), 1.4)]

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

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Sleep at night, or whenever exhaustion starts doing damage.

        Two inputs rather than one so the trace can say *why* an agent is
        turning in: the night bonus is the same tiredness, weighted again.
        """
        tiredness = need_urgency(agent.needs.energy)
        inputs = [Consideration("tired", tiredness, 0.8)]
        if world_is_night(ctx):
            inputs.append(Consideration("it is night", tiredness, NIGHT_SLEEP_BONUS))
        return inputs

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
        """Recover energy until rested - faster and safer under a roof."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt

        # A shelter is the payoff for all that wood: you rest faster in one,
        # and you stop being afraid while you are inside it.
        rate = balance.SLEEP_RATE
        shelter = shelter_near(world, agent.position, SHELTER_COMFORT_RADIUS)
        if shelter is not None:
            rate *= 1.0 + SHELTER_REST_BONUS * shelter.quality
            agent.needs.safety = min(balance.NEED_MAX, agent.needs.safety + 8.0 * dt)

        agent.needs.energy = min(balance.NEED_MAX, agent.needs.energy + rate * dt)
        return SkillStatus.DONE if agent.needs.energy >= RESTED_ENOUGH else SkillStatus.RUNNING


def world_is_night(ctx: DecisionContext) -> bool:
    """Return whether it is night, from the observation or the world clock."""
    if ctx.observation is not None:
        return ctx.observation.is_night
    return ctx.world.clock.is_night
