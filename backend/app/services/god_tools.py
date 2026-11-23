"""The observer's hands: the only sanctioned way to touch a running world.

Each tool is a plain function from `(world, request)` to what it did, run by
the engine between ticks under its lock (`sim.engine.Intervene`). They live in
the service layer rather than in `sim/` because an intervention is a thing the
*operator* does, not a rule of the world - and because spawning an agent needs
the strategy registry and the mind registry, which belong to `ai/`.

Every tool emits an event. A world that silently changed under you would make
the event feed a liar, and the feed is the main way anyone reads this thing.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from app.ai.minds import MindRegistry
from app.core.world_config import StrategyName
from app.sim.entities import (
    Agent,
    BrainType,
    DeathCause,
    ResourceKind,
    ResourceNode,
)
from app.sim.events import EventType, SimEvent
from app.sim.mortality import kill_agent
from app.sim.names import make_name
from app.sim.world import World
from app.sim.worldgen.population import life_stage_for, random_traits

DEFAULT_RADIUS = 24.0
DEFAULT_FOOD = 40.0
FOOD_PER_NODE = 8.0
PLAGUE_DAMAGE = 55.0
BOUNTY_MULTIPLIER = 3.0
SPAWN_AGE = 20.0


@dataclass(frozen=True, slots=True)
class Intervention:
    """What the observer asked for. Fields not relevant to a tool are ignored."""

    x: float | None = None
    z: float | None = None
    radius: float | None = None
    amount: float | None = None
    agent_id: int | None = None
    strategy: str | None = None
    brain_type: str | None = None


@dataclass(frozen=True, slots=True)
class Outcome:
    """What a tool actually did, for the response and the event feed."""

    affected: int = 0
    detail: str = ""


@dataclass(frozen=True, slots=True)
class GodContext:
    """What the tools need from the layers above `sim/`."""

    minds: MindRegistry
    strategies: tuple[StrategyName, ...]


def _centre(world: World, request: Intervention) -> tuple[float, float]:
    """Where the intervention lands: what was asked for, or the island's middle."""
    return (
        request.x if request.x is not None else 0.0,
        request.z if request.z is not None else 0.0,
    )


def _radius(request: Intervention) -> float:
    return request.radius if request.radius is not None else DEFAULT_RADIUS


def _agents_near(world: World, centre: tuple[float, float], radius: float) -> list[Agent]:
    """Living agents within `radius`, in id order so results are reproducible."""
    found = world.agent_index.query_radius(centre[0], centre[1], radius)
    agents = [world.agents[agent_id] for agent_id in found if agent_id in world.agents]
    return sorted((agent for agent in agents if agent.alive), key=lambda agent: agent.id)


def _emit(world: World, summary: str, position: tuple[float, float] | None = None) -> None:
    """Record an intervention in the feed, marked as the observer's doing."""
    world.events.emit(
        SimEvent(
            tick=world.clock.tick,
            type=EventType.GOD_ACTION,
            summary=summary,
            importance=9,
            position=position,
            data={"god": True},
        )
    )


# ----------------------------------------------------------------- the tools


def drop_food(world: World, request: Intervention, context: GodContext) -> Outcome:
    """Scatter berry bushes at a point - the simplest way to end a famine."""
    centre = _centre(world, request)
    total = request.amount if request.amount is not None else DEFAULT_FOOD
    radius = _radius(request)
    count = max(1, int(total // FOOD_PER_NODE))

    for index in range(count):
        # Spread them in a spiral rather than a heap, so agents arrive from
        # different directions instead of all contesting one node.
        angle = index * 2.399963  # the golden angle, for an even scatter
        distance = radius * math.sqrt((index + 0.5) / count)
        position = (
            centre[0] + math.cos(angle) * distance,
            centre[1] + math.sin(angle) * distance,
        )
        node = ResourceNode(
            id=world.next_resource_id,
            kind=ResourceKind.BERRY_BUSH,
            position=position,
            amount=FOOD_PER_NODE,
            capacity=FOOD_PER_NODE,
            regrowth_per_sim_s=0.0,
        )
        world.resources[node.id] = node
        world.next_resource_id += 1
        world.resource_index.insert(node.id, *position)

    _emit(world, f"A gift of food appeared: {count} bushes", centre)
    return Outcome(
        affected=count, detail=f"{count} bushes carrying {count * FOOD_PER_NODE:.0f} food"
    )


def drought(world: World, request: Intervention, context: GodContext) -> Outcome:
    """Empty the water in a radius and stop it coming back.

    Water is normally infinite, which is what makes this interesting: it is
    the one resource agents never have to plan around, until now.
    """
    centre = _centre(world, request)
    radius = _radius(request)
    affected = 0

    for node_id in world.resource_index.query_radius(centre[0], centre[1], radius):
        node = world.resources.get(node_id)
        if node is None or node.kind is not ResourceKind.WATER:
            continue
        node.infinite = False
        node.amount = 0.0
        node.regrowth_per_sim_s = 0.0
        affected += 1

    _emit(world, f"A drought dried up {affected} watering spots", centre)
    return Outcome(affected=affected, detail=f"{affected} water nodes dried up")


def bounty(world: World, request: Intervention, context: GodContext) -> Outcome:
    """Fill every resource node in a radius and speed up its regrowth."""
    centre = _centre(world, request)
    radius = _radius(request)
    multiplier = request.amount if request.amount is not None else BOUNTY_MULTIPLIER
    affected = 0

    for node_id in world.resource_index.query_radius(centre[0], centre[1], radius):
        node = world.resources.get(node_id)
        if node is None or node.kind is ResourceKind.WATER:
            continue
        node.amount = node.capacity
        if node.regrowth_per_sim_s > 0.0:
            node.regrowth_per_sim_s *= max(1.0, multiplier)
        affected += 1

    _emit(world, f"A good season: {affected} patches came back to life", centre)
    return Outcome(affected=affected, detail=f"{affected} nodes refilled")


def plague(world: World, request: Intervention, context: GodContext) -> Outcome:
    """Take a bite out of the health of everyone nearby.

    Lethal for the already-weak, survivable for the healthy - which is the
    point: a plague should reshape a society, not empty the island.
    """
    centre = _centre(world, request)
    radius = _radius(request)
    severity = request.amount if request.amount is not None else PLAGUE_DAMAGE
    victims = _agents_near(world, centre, radius)
    died = 0

    for agent in victims:
        agent.health = max(0.0, agent.health - severity)
        if agent.health <= 0.0:
            kill_agent(world, agent, DeathCause.PLAGUE)
            died += 1

    _emit(world, f"A plague swept {len(victims)} agents; {died} did not survive", centre)
    return Outcome(affected=len(victims), detail=f"{len(victims)} infected, {died} died")


def spawn_agent(world: World, request: Intervention, context: GodContext) -> Outcome:
    """Drop one new agent into the world, with a chosen strategy and brain."""
    if len(world.living_agents()) >= world.config.max_agents:
        return Outcome(detail="the island is already at its agent limit")

    centre = _centre(world, request)
    rng = world.rngs["spawn"]
    strategy: StrategyName = "TitForTat"
    for known in context.strategies:
        if known == request.strategy:
            strategy = known
            break
    brain = BrainType.LLM if request.brain_type == "llm" else BrainType.UTILITY

    agent = Agent(
        id=world.next_agent_id,
        name=make_name(rng, {other.name for other in world.agents.values()}),
        position=centre,
        traits=random_traits(rng, world.config.trait_bias),
        strategy=strategy,
        brain_type=brain,
        age=SPAWN_AGE,
        life_stage=life_stage_for(SPAWN_AGE),
    )
    world.agents[agent.id] = agent
    world.next_agent_id += 1
    world.agent_index.insert(agent.id, *centre)
    # The living-agent list is cached per tick; without this the new agent is
    # invisible to every system and to the API until the next tick.
    world.invalidate_living()
    # A mind, or the agent would be unable to perceive, decide or remember.
    context.minds.require(agent.id)

    _emit(world, f"{agent.name} appeared out of nowhere, playing {strategy}", centre)
    return Outcome(affected=1, detail=f"{agent.name} (#{agent.id}) playing {strategy}")


def smite(world: World, request: Intervention, context: GodContext) -> Outcome:
    """Kill one named agent. The bluntest instrument in the box."""
    agent = world.agents.get(request.agent_id) if request.agent_id is not None else None
    if agent is None or not agent.alive:
        return Outcome(detail="no such living agent")

    kill_agent(world, agent, DeathCause.SMITE)

    _emit(world, f"{agent.name} was struck down", agent.position)
    return Outcome(affected=1, detail=f"{agent.name} (#{agent.id}) is dead")


type GodTool = Callable[[World, Intervention, GodContext], Outcome]

TOOLS: Mapping[str, GodTool] = {
    "drop_food": drop_food,
    "drought": drought,
    "bounty": bounty,
    "plague": plague,
    "spawn_agent": spawn_agent,
    "smite": smite,
}
"""Every tool, by the name used in `POST /api/god/{action}`."""
