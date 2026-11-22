"""Shared mechanics for skills: finding things, and walking to them.

Target selection breaks ties by node id, never by iteration order, so two runs
with the same seed always pick the same bush.
"""

import math

from app.sim import balance
from app.sim.entities import Agent, LifeStage, ResourceKind, ResourceNode
from app.sim.world import World


def walk_speed(agent: Agent) -> float:
    """Return how fast `agent` walks, by life stage and energy."""
    speed = balance.WALK_SPEED
    if agent.life_stage is LifeStage.CHILD:
        speed *= balance.CHILD_SPEED_FACTOR
    elif agent.life_stage is LifeStage.ELDER:
        speed *= balance.ELDER_SPEED_FACTOR
    # Running on empty is slow.
    if agent.needs.energy < balance.NEED_URGENT:
        speed *= 0.7
    return speed


def stop(agent: Agent) -> None:
    """Zero an agent's velocity."""
    agent.velocity = (0.0, 0.0)


def distance_to(agent: Agent, target: tuple[float, float]) -> float:
    """Return the planar distance from `agent` to `target`."""
    return math.hypot(target[0] - agent.position[0], target[1] - agent.position[1])


def steer_towards(agent: Agent, target: tuple[float, float], speed: float | None = None) -> bool:
    """Point `agent` at `target` and return whether it has arrived."""
    distance = distance_to(agent, target)
    if distance <= balance.ARRIVAL_DISTANCE:
        stop(agent)
        return True
    pace = walk_speed(agent) if speed is None else speed
    scale = pace / distance
    agent.velocity = (
        (target[0] - agent.position[0]) * scale,
        (target[1] - agent.position[1]) * scale,
    )
    return False


def steer_away(agent: Agent, threat: tuple[float, float], speed: float | None = None) -> None:
    """Point `agent` directly away from `threat`."""
    offset_x = agent.position[0] - threat[0]
    offset_z = agent.position[1] - threat[1]
    length = math.hypot(offset_x, offset_z)
    if length < 1e-6:
        agent.velocity = (walk_speed(agent), 0.0)
        return
    pace = (walk_speed(agent) if speed is None else speed) * 1.2
    agent.velocity = (offset_x / length * pace, offset_z / length * pace)


def nearest_resource(
    world: World,
    agent: Agent,
    kinds: frozenset[ResourceKind],
    radius: float = balance.VISION_RADIUS,
) -> ResourceNode | None:
    """Return the closest non-depleted node of one of `kinds`, or `None`.

    Not memoised, though a third of these calls within a tick are the same
    question asked twice. Caching them per tick was tried and reverted: the
    world changes *during* a tick (a skill depletes a node, a god tool drops
    food), so a cached answer goes stale in a way nothing would notice at
    runtime - and the measured gain was about 4%, inside the noise. See
    ADR 0005.
    """
    x, z = agent.position
    best: ResourceNode | None = None
    best_distance = float("inf")

    for node_id in sorted(world.resource_index.query_radius(x, z, radius)):
        node = world.resources.get(node_id)
        if node is None or node.kind not in kinds or node.depleted:
            continue
        distance = (node.position[0] - x) ** 2 + (node.position[1] - z) ** 2
        if distance < best_distance:
            best_distance, best = distance, node
    return best


def nearest_threat(world: World, agent: Agent) -> Agent | None:
    """Return the closest aggressive neighbour inside the threat radius."""
    best: Agent | None = None
    best_distance = float("inf")
    limit = balance.THREAT_RADIUS**2
    x, z = agent.position

    for other_id in sorted(world.agent_index.neighbours(agent.id, balance.THREAT_RADIUS)):
        other = world.agents.get(other_id)
        if other is None or not other.alive:
            continue
        if other.traits.aggression < balance.THREAT_AGGRESSION:
            continue
        distance = (other.position[0] - x) ** 2 + (other.position[1] - z) ** 2
        if distance <= limit and distance < best_distance:
            best_distance, best = distance, other
    return best


def need_urgency(level: float) -> float:
    """Map a need level in `0..100` to an urgency in `0..1` (100 -> 0)."""
    return max(0.0, min(1.0, (balance.NEED_MAX - level) / balance.NEED_MAX))
