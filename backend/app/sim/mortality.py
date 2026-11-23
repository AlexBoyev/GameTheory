"""The one way an agent dies (SPEC section 4.2).

Its own module because two callers need it and they sit on opposite sides of
the layering: `LifecycleSystem` kills agents that run out of health, and the
god tools kill them because somebody clicked a button.

They used not to share. `plague` and `smite` set `alive = False`, bumped
`world.deaths` and stopped there - so a smitten agent was never removed from
the spatial index (neighbours kept finding a corpse that was not there),
never left a body, and never produced a `DEATH` event, which meant the feed
quietly disagreed with the population counter. Dying is one thing; it belongs
in one function.
"""

from app.sim.entities import Agent, AgentState, DeathCause
from app.sim.events import EventType, SimEvent
from app.sim.world import World
from app.sim.worldgen.resources import add_corpse


def kill_agent(world: World, agent: Agent, cause: DeathCause | None = None) -> None:
    """Mark `agent` dead, drop it from the index, and leave a corpse.

    `cause` overrides whatever the agent was already heading towards; passing
    none keeps the cause the needs system recorded, and falls back to
    starvation, which is how an agent runs out of health unaided.
    """
    if not agent.alive:
        return

    resolved = cause or agent.death_cause or DeathCause.STARVATION
    agent.death_cause = resolved
    agent.alive = False
    agent.health = 0.0
    agent.state = AgentState.DEAD
    agent.velocity = (0.0, 0.0)
    agent.current_skill = None

    world.agent_index.remove(agent.id)
    world.deaths += 1
    world.deaths_by_cause[resolved.value] = world.deaths_by_cause.get(resolved.value, 0) + 1
    # `living_agents()` is cached per tick and read by every system and the
    # API; without this the dead keep walking until the next tick.
    world.invalidate_living()

    corpse = add_corpse(world, agent.position)
    world.resource_index.insert(corpse.id, corpse.position[0], corpse.position[1])

    world.events.emit(
        SimEvent(
            tick=world.clock.tick,
            type=EventType.DEATH,
            summary=f"{agent.name} died of {resolved.value.replace('_', ' ')}",
            actors=(agent.id,),
            importance=6,
            position=agent.position,
            data={"cause": resolved.value, "age": round(agent.age, 1)},
        )
    )
