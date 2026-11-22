"""Houses: gathering wood and putting up a shelter (SPEC section 7.3).

A shelter is the first thing an agent builds that outlives the moment. It
makes sleep faster and safer, and once tribes exist the cluster of huts round
a camp is what a tribe physically *is*.
"""

from pydantic import BaseModel

from app.ai.brains.base import DecisionContext
from app.ai.skills.base import Consideration, NoParams, Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import nearest_resource, steer_towards, stop
from app.core.result import OK_NONE, Err, Result
from app.sim import balance
from app.sim.entities import Agent, AgentState, ResourceKind, Shelter
from app.sim.events import EventType, SimEvent
from app.sim.world import World

WOOD_PER_SHELTER = 6.0
BUILD_DURATION = 12.0
MIN_SHELTER_SPACING = 6.0
CHOP_RATE = 1.6

TREES: frozenset[ResourceKind] = frozenset({ResourceKind.TREE})


def shelter_for(world: World, agent: Agent) -> Shelter | None:
    """Return this agent's own shelter, if it has one."""
    for shelter_id in sorted(world.shelters):
        shelter = world.shelters[shelter_id]
        if shelter.owner_id == agent.id:
            return shelter
    return None


def nearest_shelter_distance(world: World, position: tuple[float, float]) -> float:
    """Distance to the closest shelter, or infinity if there are none."""
    best = float("inf")
    for shelter in world.shelters.values():
        distance = (shelter.position[0] - position[0]) ** 2 + (
            shelter.position[1] - position[1]
        ) ** 2
        best = min(best, distance**0.5)
    return best


class GatherWood(Skill):
    """Chop wood from a tree - the input to everything built."""

    name = "GatherWood"
    description = "Collect wood from a tree."
    category = SkillCategory.SURVIVAL
    Params = NoParams
    visual_state = AgentState.GATHER

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a tree within the agent's known territory, and room to carry.

        Trees get the landmark radius for the same reason water does: a tree
        does not move, and an animal knows where the wood is. At vision range
        only, the dozen trees on an island this size were effectively
        invisible and nobody ever built anything.
        """
        if agent.inventory.wood >= WOOD_PER_SHELTER:
            return Err("carrying enough wood")
        if nearest_resource(world, agent, TREES, balance.LANDMARK_RADIUS) is None:
            return Err("no tree within reach")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Only worth doing when comfortable and without a roof."""
        if agent.inventory.wood >= WOOD_PER_SHELTER:
            return []
        if shelter_for(ctx.world, agent) is not None:
            return []
        comfort = min(agent.needs.hunger, agent.needs.thirst) / balance.NEED_MAX
        if comfort < 0.5:
            return []
        # Value in [0, 1], magnitude in the weight: `apply_curve` clamps the
        # value, so a loyal agent's 1.4 would quietly become 1.0.
        return [
            Consideration("comfortable enough to plan", comfort, 0.3 * (0.4 + agent.traits.loyalty))
        ]

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Walk to the nearest tree."""
        tree = nearest_resource(world, agent, TREES, balance.LANDMARK_RADIUS)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"node": -1 if tree is None else tree.id, "arrived": False},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Chop until carrying enough for a hut."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        tree = world.resources.get(int(run.state["node"]))
        if tree is None or tree.depleted:
            stop(agent)
            return SkillStatus.FAILED

        if not run.state["arrived"]:
            if not steer_towards(agent, tree.position):
                return SkillStatus.RUNNING
            run.state["arrived"] = True

        taken = min(CHOP_RATE * dt, tree.amount, WOOD_PER_SHELTER - agent.inventory.wood)
        tree.amount -= taken
        agent.inventory.wood += taken

        if agent.inventory.wood >= WOOD_PER_SHELTER or tree.depleted:
            stop(agent)
            return SkillStatus.DONE
        return SkillStatus.RUNNING


class BuildShelter(Skill):
    """Put up a hut. Costs wood and time; pays back every night."""

    name = "BuildShelter"
    description = "Build a shelter from gathered wood."
    category = SkillCategory.SURVIVAL
    Params = NoParams
    visual_state = AgentState.BUILD
    cooldown = 120.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require wood, dry standable ground, and elbow room."""
        if agent.inventory.wood < WOOD_PER_SHELTER:
            return Err("not enough wood")
        if shelter_for(world, agent) is not None:
            return Err("already have a shelter")
        if not world.terrain.is_walkable(*agent.position):
            return Err("cannot build here")
        if nearest_shelter_distance(world, agent.position) < MIN_SHELTER_SPACING:
            return Err("too close to another shelter")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """With the wood in hand, building is close to a priority."""
        if agent.inventory.wood < WOOD_PER_SHELTER:
            return []
        return [Consideration("wood in hand", 1.0, 0.65)]

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Begin construction where we stand."""
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"x": agent.position[0], "z": agent.position[1]},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Work on it, then raise the hut."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        if run.elapsed < BUILD_DURATION:
            return SkillStatus.RUNNING
        if agent.inventory.wood < WOOD_PER_SHELTER:
            return SkillStatus.FAILED

        agent.inventory.wood -= WOOD_PER_SHELTER
        shelter = Shelter(
            id=world.next_shelter_id,
            position=(float(run.state["x"]), float(run.state["z"])),
            owner_id=agent.id,
            tribe_id=agent.tribe_id,
            quality=0.6 + 0.4 * agent.traits.loyalty,
            built_tick=world.clock.tick,
        )
        world.shelters[shelter.id] = shelter
        world.next_shelter_id += 1
        self.services.ledger.shelters_built += 1

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.SHELTER_BUILT,
                summary=f"{agent.name} built a shelter",
                actors=(agent.id,),
                importance=5,
                position=shelter.position,
            )
        )
        return SkillStatus.DONE
