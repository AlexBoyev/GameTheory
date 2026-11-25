"""Compact wire encoding of a world state (SPEC section 8).

Flat float arrays rather than objects: at 20 Hz with hundreds of agents, the
difference between `[id, x, z, ...]` and `{"id": ..., "x": ...}` is most of the
bandwidth and most of the JSON parse time in the browser.
"""

from dataclasses import dataclass, field

from app.sim.entities import AgentState, Biome, BrainType, ResourceKind, TribeRole
from app.sim.world import World

FRAME_STRIDE = 7
"""Values per agent: id, x, z, heading, state, tribe, flags."""

RESOURCE_STRIDE = 6
"""Values per resource: id, x, z, kind, amount, capacity.

Capacity travels with the node so a client that connects to a world already in
progress can still draw a half-eaten bush at the right size.
"""

AGENT_STATE_CODES: tuple[str, ...] = tuple(state.value for state in AgentState)
"""Index = wire code for an agent state; the frontend maps these to emoji."""

BIOME_CODES: tuple[str, ...] = tuple(biome.value for biome in Biome)
"""Index = wire code for a biome, matching the terrain biome map."""

RESOURCE_CODES: tuple[str, ...] = tuple(kind.value for kind in ResourceKind)
"""Index = wire code for a resource kind."""

_STATE_INDEX: dict[AgentState, int] = {state: index for index, state in enumerate(AgentState)}
_RESOURCE_INDEX: dict[ResourceKind, int] = {kind: index for index, kind in enumerate(ResourceKind)}

FLAG_LLM = 1
FLAG_LEADER = 2
FLAG_ASLEEP = 4
FLAG_CHILD = 8


@dataclass(frozen=True, slots=True)
class WorldFrame:
    """One broadcastable snapshot of the moving parts."""

    tick: int
    agents: list[float]
    time_of_day: float
    day: int
    season: str
    population: int
    status: str
    speed: float
    skip_remaining: int = 0
    """Ticks still owed to a skip. Carried on the frame rather than left to
    the 1 Hz state poll so a progress bar moves while the skip runs."""

    resource_fullness: dict[int, float] = field(default_factory=dict)


def agent_flags(agent_brain: BrainType, role: TribeRole, state: AgentState, child: bool) -> int:
    """Pack the booleans the renderer needs into one integer."""
    flags = 0
    if agent_brain is BrainType.LLM:
        flags |= FLAG_LLM
    if role is TribeRole.LEADER:
        flags |= FLAG_LEADER
    if state is AgentState.SLEEP:
        flags |= FLAG_ASLEEP
    if child:
        flags |= FLAG_CHILD
    return flags


def encode_agents(world: World) -> list[float]:
    """Return the flat, stride-7 agent array in stable id order."""
    flat: list[float] = []
    for agent in world.living_agents():
        flat.extend(
            (
                float(agent.id),
                round(agent.position[0], 3),
                round(agent.position[1], 3),
                round(agent.heading, 3),
                float(_STATE_INDEX[agent.state]),
                float(-1 if agent.tribe_id is None else agent.tribe_id),
                float(
                    agent_flags(
                        agent.brain_type,
                        agent.role,
                        agent.state,
                        child=not agent.is_adult,
                    )
                ),
            )
        )
    return flat


def encode_resources(world: World) -> list[float]:
    """Return the flat, stride-5 array of every resource node."""
    flat: list[float] = []
    for node_id in sorted(world.resources):
        node = world.resources[node_id]
        flat.extend(
            (
                float(node.id),
                round(node.position[0], 2),
                round(node.position[1], 2),
                float(_RESOURCE_INDEX[node.kind]),
                round(node.amount, 2),
                round(node.capacity, 2),
            )
        )
    return flat


FULLNESS_STEPS = 50
"""Resource fullness is quantised to 2% steps before it goes on the wire.

Regrowth moves every node a fraction of a unit per tick, so sending exact
amounts made almost all ~200 nodes "changed" on every frame - several KB per
frame to animate a bush shrinking by a pixel. Two percent is below what the
renderer can show and cuts the per-frame resource payload by about 70%.
"""


def resource_fullness(world: World) -> dict[int, float]:
    """Return `{node_id: fullness}` in `[0, 1]`, quantised for delta sending."""
    fullness: dict[int, float] = {}
    for node_id, node in world.resources.items():
        if node.infinite or node.capacity <= 0:
            fullness[node_id] = 1.0
            continue
        ratio = max(0.0, min(1.0, node.amount / node.capacity))
        fullness[node_id] = round(ratio * FULLNESS_STEPS) / FULLNESS_STEPS
    return fullness


def encode_frame(world: World, status: str, speed: float, skip_remaining: int = 0) -> WorldFrame:
    """Build a `WorldFrame` from the current world state."""
    return WorldFrame(
        tick=world.clock.tick,
        agents=encode_agents(world),
        time_of_day=round(world.clock.time_of_day, 4),
        day=world.clock.day,
        season=world.clock.season,
        population=world.population,
        status=status,
        speed=speed,
        skip_remaining=skip_remaining,
        resource_fullness=resource_fullness(world),
    )
