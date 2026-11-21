"""Integrating velocity into position, and keeping agents on dry land."""

import math

from app.sim.world import World


class MovementSystem:
    """Moves agents, blocks them from walking into water, reindexes them.

    Skills set `agent.velocity`; this is the only place position changes, so
    "can an agent be here?" is answered once instead of in every skill.
    """

    name = "movement"

    __slots__ = ()

    def step(self, world: World, dt: float) -> None:
        """Advance positions by `dt` and rebuild the agent spatial index."""
        terrain = world.terrain
        moved = False

        for agent in world.living_agents():
            velocity_x, velocity_z = agent.velocity
            if velocity_x == 0.0 and velocity_z == 0.0:
                continue

            current_x, current_z = agent.position
            next_x = current_x + velocity_x * dt
            next_z = current_z + velocity_z * dt

            if not terrain.is_walkable(next_x, next_z):
                # Slide along whichever axis is still land, so agents follow
                # the shoreline instead of sticking to it.
                if terrain.is_walkable(next_x, current_z):
                    next_z = current_z
                elif terrain.is_walkable(current_x, next_z):
                    next_x = current_x
                else:
                    agent.velocity = (0.0, 0.0)
                    continue

            agent.position = (next_x, next_z)
            agent.heading = math.atan2(velocity_x, velocity_z)
            moved = True

        if moved:
            world.agent_index.rebuild(
                (agent.id, agent.position[0], agent.position[1]) for agent in world.living_agents()
            )
