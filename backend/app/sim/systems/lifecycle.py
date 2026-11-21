"""Ageing, death and what a body leaves behind (SPEC section 4.2)."""

from app.sim import balance
from app.sim.entities import Agent, AgentState, DeathCause, life_stage_for
from app.sim.events import EventType, SimEvent
from app.sim.world import World
from app.sim.worldgen.resources import add_corpse


class LifecycleSystem:
    """Ages agents, kills the ones that run out of health, leaves corpses."""

    name = "lifecycle"

    __slots__ = ()

    def step(self, world: World, dt: float) -> None:
        """Advance ages by `dt` and resolve any deaths."""
        years_per_sim_s = balance.AGE_YEARS_PER_DAY / world.clock.day_seconds
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
            self._kill(world, agent)

    @staticmethod
    def _kill(world: World, agent: Agent) -> None:
        """Mark `agent` dead, drop it from the index and leave a corpse."""
        agent.alive = False
        agent.state = AgentState.DEAD
        agent.velocity = (0.0, 0.0)
        agent.current_skill = None
        cause = agent.death_cause or DeathCause.STARVATION
        agent.death_cause = cause

        world.agent_index.remove(agent.id)
        world.deaths += 1
        world.invalidate_living()

        corpse = add_corpse(world, agent.position)
        world.resource_index.insert(corpse.id, corpse.position[0], corpse.position[1])

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.DEATH,
                summary=f"{agent.name} died of {cause.value.replace('_', ' ')}",
                actors=(agent.id,),
                importance=6,
                position=agent.position,
                data={"cause": cause.value, "age": round(agent.age, 1)},
            )
        )
