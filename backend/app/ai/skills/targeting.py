"""Choosing who a social skill is about.

Every skill that does something *to* somebody needs the same two questions
answered - who is nearby, and who did the caller mean - so they live here
rather than in `social.py`. Combat, manipulation and the tribe skills were all
importing `social` to reach them, which made a module of skills look like a
utility module.
"""

from pydantic import BaseModel, ConfigDict

from app.sim.entities import Agent
from app.sim.world import INTERACTION_RADIUS, World


class TargetParams(BaseModel):
    """Who to do this to; defaults to the nearest suitable neighbour."""

    model_config = ConfigDict(extra="forbid")

    target: int | None = None


def nearby_agents(world: World, agent: Agent, radius: float = INTERACTION_RADIUS) -> list[Agent]:
    """Living neighbours within `radius`, in stable id order.

    Through `World.neighbours_within`, which memoises the spatial query for
    the rest of the tick: the brain asks this once per social skill it
    scores, which measured at five to seven times per deciding agent.
    """
    found: list[Agent] = []
    for other_id in sorted(world.neighbours_within(agent.id, radius)):
        other = world.agents.get(other_id)
        if other is not None and other.alive:
            found.append(other)
    return found


def resolve_target(world: World, agent: Agent, params: BaseModel) -> Agent | None:
    """Return the requested neighbour, or the nearest one."""
    if isinstance(params, TargetParams) and params.target is not None:
        other = world.agents.get(params.target)
        return other if other is not None and other.alive else None
    neighbours = nearby_agents(world, agent)
    return neighbours[0] if neighbours else None
