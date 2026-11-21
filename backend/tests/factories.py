"""Helpers for building precise little scenarios inside a generated world."""

from app.ai.skills.base import Skill, SkillStatus
from app.sim.entities import Agent, ResourceKind, ResourceNode
from app.sim.world import World


def place(world: World, kind: ResourceKind, position: tuple[float, float]) -> ResourceNode:
    """Add a full resource node at `position` and index it."""
    node = ResourceNode(
        id=world.next_resource_id,
        kind=kind,
        position=position,
        amount=10.0,
        capacity=10.0,
        infinite=kind is ResourceKind.WATER,
    )
    world.resources[node.id] = node
    world.next_resource_id += 1
    world.resource_index.insert(node.id, *position)
    return node


def centre_agent(world: World) -> Agent:
    """Move an agent to the middle of the island, standing still."""
    agent = world.living_agents()[0]
    agent.position = (0.0, 0.0)
    agent.velocity = (0.0, 0.0)
    world.agent_index.insert(agent.id, 0.0, 0.0)
    return agent


def clear_resources(world: World) -> None:
    """Empty the world of resources, for tests that place their own."""
    world.resources.clear()
    world.resource_index.clear()


def run_until_done(
    skill: Skill,
    world: World,
    agent: Agent,
    params: object,
    limit: int = 400,
) -> SkillStatus:
    """Start and step a skill to completion, applying velocity as movement would."""
    run = skill.start(agent, world, params)  # type: ignore[arg-type]
    status = SkillStatus.RUNNING
    for _ in range(limit):
        status = skill.step(run, world, world.clock.dt)
        if status is not SkillStatus.RUNNING:
            return status
        agent.position = (
            agent.position[0] + agent.velocity[0] * world.clock.dt,
            agent.position[1] + agent.velocity[1] * world.clock.dt,
        )
    return status
