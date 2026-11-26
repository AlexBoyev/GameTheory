"""Shared mechanics for skills: finding things, and walking to them.

Target selection breaks ties by node id, never by iteration order, so two runs
with the same seed always pick the same bush.
"""

import math

from app.ai.skills.base import SkillRun
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

    The *answer* is still computed every time, because the world changes
    during a tick - a skill depletes a node, a god tool drops food - and a
    cached answer would go stale in a way nothing would notice at runtime
    (ADR 0005, where caching it was tried and reverted for ~4%).

    What is memoised is the *scan* underneath: which node ids lie within
    `radius`. Nodes never move, so that set changes only when one is added
    or removed, and `World.resources_within` notices. The kind and depletion
    tests below still run on every call. Measured at 300 agents: 101 of
    these a tick, 56% of them repeats.
    """
    x, z = agent.position
    best: ResourceNode | None = None
    best_distance = float("inf")

    for node_id in sorted(world.resources_within(agent.id, agent.position, radius)):
        node = world.resources.get(node_id)
        if node is None or node.kind not in kinds or node.depleted:
            continue
        distance = (node.position[0] - x) ** 2 + (node.position[1] - z) ** 2
        if distance < best_distance:
            best_distance, best = distance, node
    return best


MAX_RETARGETS = 3
"""How many times a gathering trip will walk on to the next node.

Measured at 300 agents: 65% of wood trips and 51% of food trips ended in
failure, after about ten ticks of walking, because somebody emptied the node
while the agent was on its way. That is the commons working as intended - but
*giving up* is not what it means. The agent stood still, the brain scored
thirty-odd skills again (0.32 ms, and those re-decisions were 75% of all
decisions and 45% of a tick at that size), and it almost always chose the
same skill and the next-nearest node. Walking straight there is the same
outcome without the deliberation.

Three covers ordinary contention and is small enough that an agent in a
picked-clean region gives up and does something else rather than touring the
island. The trip is still interruptible, so real hunger or a threat still
takes it off the errand.
"""


def retarget(
    run: SkillRun,
    world: World,
    agent: Agent,
    kinds: frozenset[ResourceKind],
    radius: float = balance.VISION_RADIUS,
) -> bool:
    """Point a gathering run at the next node, or report that there is none.

    Shared by the two gatherers because the state they keep is the same
    (`node`, `arrived`, `retargets`) and so is the reason for keeping it.
    """
    used = int(run.state.get("retargets", 0))
    if used >= MAX_RETARGETS:
        return False
    node = nearest_resource(world, agent, kinds, radius)
    if node is None:
        return False
    run.state["node"] = node.id
    run.state["arrived"] = False
    run.state["retargets"] = used + 1
    return True


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
