"""Ageing, death and what a body leaves behind (SPEC section 4.2)."""

from app.sim import balance
from app.sim.entities import Agent, DeathCause, life_stage_for
from app.sim.mortality import kill_agent
from app.sim.world import World


class LifecycleSystem:
    """Ages agents, kills the ones that run out of health, leaves corpses."""

    name = "lifecycle"

    __slots__ = ()

    def step(self, world: World, dt: float) -> None:
        """Advance ages by `dt` and resolve any deaths."""
        years_per_sim_s = world.config.age_years_per_day / world.clock.day_seconds
        aged = years_per_sim_s * dt
        dying: list[Agent] = []

        for agent in world.living_agents():
            agent.age += aged
            agent.life_stage = life_stage_for(agent.age)

            if agent.age >= balance.MAX_AGE:
                agent.health = max(0.0, agent.health - balance.OLD_AGE_DAMAGE * dt)
                agent.death_cause = DeathCause.OLD_AGE

            if agent.health <= 0.0:
                dying.append(agent)

        for agent in dying:
            kill_agent(world, agent)
