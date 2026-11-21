"""Needs decay, and the health consequences of letting one hit zero."""

from app.sim import balance
from app.sim.entities import Agent, AgentState, DeathCause
from app.sim.world import World

WINTER_HUNGER_FACTOR = 1.25
"""Winter burns more calories (SPEC 3.2)."""


class NeedsSystem:
    """Decays the five drives, then applies damage or slow healing.

    Safety drifts back up here and is pushed down by perception, so an agent
    calms down a few seconds after the aggressive neighbour wanders off.
    """

    name = "needs"

    __slots__ = ()

    def step(self, world: World, dt: float) -> None:
        """Advance every living agent's needs and health by `dt`."""
        night = world.clock.is_night
        winter = world.clock.season == "winter"
        hunger_rate = balance.HUNGER_DECAY * (WINTER_HUNGER_FACTOR if winter else 1.0)
        energy_rate = balance.ENERGY_DECAY_NIGHT if night else balance.ENERGY_DECAY

        for agent in world.living_agents():
            needs = agent.needs
            asleep = agent.state is AgentState.SLEEP

            needs.hunger = max(0.0, needs.hunger - hunger_rate * dt)
            needs.thirst = max(0.0, needs.thirst - balance.THIRST_DECAY * dt)
            if not asleep:
                needs.energy = max(0.0, needs.energy - energy_rate * dt)
            needs.social = max(0.0, needs.social - balance.SOCIAL_DECAY * dt)
            needs.safety = min(balance.NEED_MAX, needs.safety + balance.SAFETY_RECOVERY * dt)

            _update_health(agent, dt)


def _update_health(agent: Agent, dt: float) -> None:
    """Damage an agent whose needs bottomed out, or heal a comfortable one.

    The worst-hit need also records the likely death cause, so the lifecycle
    system can report *why* an agent died rather than just that it did.
    """
    needs = agent.needs
    damage = 0.0
    cause: DeathCause | None = None

    if needs.thirst <= 0.0:
        damage += balance.DEHYDRATION_DAMAGE
        cause = DeathCause.DEHYDRATION
    if needs.hunger <= 0.0:
        damage += balance.STARVATION_DAMAGE
        # Thirst kills faster, so it keeps the blame when both are empty.
        cause = cause or DeathCause.STARVATION
    if needs.energy <= 0.0:
        damage += balance.EXHAUSTION_DAMAGE
        cause = cause or DeathCause.STARVATION

    if damage > 0.0:
        agent.health = max(0.0, agent.health - damage * dt)
        agent.death_cause = cause
        return

    comfortable = min(needs.hunger, needs.thirst, needs.energy) > balance.HEALTH_REGEN_THRESHOLD
    if comfortable and agent.health < balance.NEED_MAX:
        agent.health = min(balance.NEED_MAX, agent.health + balance.HEALTH_REGEN * dt)
        agent.death_cause = None
