"""Needs decay, damage, healing, ageing and death."""

import pytest

from app.sim import balance
from app.sim.entities import AgentState, DeathCause, LifeStage, ResourceKind, life_stage_for
from app.sim.systems import LifecycleSystem, NeedsSystem
from app.sim.systems.needs import WINTER_HUNGER_FACTOR
from app.sim.world import World

DT = 1.0


def noon(world: World) -> None:
    """Move the clock to midday - a world starts at tick 0, i.e. midnight."""
    world.clock = world.clock.advance(int(world.clock.day_seconds / 2 / world.clock.dt))
    assert not world.clock.is_night


def test_needs_decay_at_the_configured_rates(world: World) -> None:
    noon(world)
    agent = world.living_agents()[0]
    before = (agent.needs.hunger, agent.needs.thirst, agent.needs.energy)

    NeedsSystem().step(world, DT)

    assert agent.needs.hunger == pytest.approx(before[0] - balance.HUNGER_DECAY * DT)
    assert agent.needs.thirst == pytest.approx(before[1] - balance.THIRST_DECAY * DT)
    assert agent.needs.energy == pytest.approx(before[2] - balance.ENERGY_DECAY * DT)


def test_nights_are_more_tiring_than_days(world: World) -> None:
    agent = world.living_agents()[0]
    assert world.clock.is_night, "a world starts at midnight"

    NeedsSystem().step(world, DT)
    at_night = 100.0 - agent.needs.energy

    agent.needs.energy = 100.0
    noon(world)
    NeedsSystem().step(world, DT)
    by_day = 100.0 - agent.needs.energy

    assert at_night > by_day
    assert at_night == pytest.approx(balance.ENERGY_DECAY_NIGHT * DT)


def test_needs_never_go_below_zero(world: World) -> None:
    agent = world.living_agents()[0]
    agent.needs.hunger = 0.1
    agent.needs.thirst = 0.1

    NeedsSystem().step(world, 10.0)

    assert agent.needs.hunger == 0.0
    assert agent.needs.thirst == 0.0


def test_sleeping_agents_keep_their_energy(world: World) -> None:
    agent = world.living_agents()[0]
    agent.state = AgentState.SLEEP
    agent.needs.energy = 50.0

    NeedsSystem().step(world, DT)

    assert agent.needs.energy == 50.0


def test_winter_burns_more_calories(world: World) -> None:
    agent = world.living_agents()[0]
    agent.needs.hunger = 80.0
    world.clock = world.clock.__class__(
        tick=0,
        dt=world.clock.dt,
        day_seconds=world.clock.day_seconds,
        days_per_season=world.clock.days_per_season,
        season_offset=3,
    )
    assert world.clock.season == "winter"

    NeedsSystem().step(world, DT)

    assert agent.needs.hunger == pytest.approx(
        80.0 - balance.HUNGER_DECAY * WINTER_HUNGER_FACTOR * DT
    )


def test_an_empty_stomach_costs_health_and_records_the_cause(world: World) -> None:
    agent = world.living_agents()[0]
    agent.needs.hunger = 0.0
    agent.health = 50.0

    NeedsSystem().step(world, DT)

    assert agent.health < 50.0
    assert agent.death_cause is DeathCause.STARVATION


def test_thirst_takes_the_blame_over_hunger(world: World) -> None:
    agent = world.living_agents()[0]
    agent.needs.hunger = 0.0
    agent.needs.thirst = 0.0

    NeedsSystem().step(world, DT)

    assert agent.death_cause is DeathCause.DEHYDRATION


def test_a_comfortable_agent_heals(world: World) -> None:
    agent = world.living_agents()[0]
    agent.health = 50.0
    agent.needs.hunger = 100.0
    agent.needs.thirst = 100.0
    agent.needs.energy = 100.0

    NeedsSystem().step(world, DT)

    assert agent.health > 50.0
    assert agent.death_cause is None


def test_death_leaves_a_corpse_and_an_event(world: World) -> None:
    agent = world.living_agents()[0]
    agent.health = 0.0
    agent.death_cause = DeathCause.STARVATION
    corpses_before = sum(1 for node in world.resources.values() if node.kind is ResourceKind.CORPSE)

    LifecycleSystem().step(world, DT)

    assert not agent.alive
    assert agent.state is AgentState.DEAD
    assert agent.id not in world.agent_index
    assert world.deaths == 1
    corpses_after = sum(1 for node in world.resources.values() if node.kind is ResourceKind.CORPSE)
    assert corpses_after == corpses_before + 1

    drained = world.events.drain()
    assert any(event.type.value == "death" and agent.name in event.summary for event in drained)


def test_agents_age_and_eventually_die_of_old_age(world: World) -> None:
    agent = world.living_agents()[0]
    agent.age = balance.MAX_AGE + 1.0
    agent.health = 1.0

    LifecycleSystem().step(world, 10.0)

    assert not agent.alive
    assert agent.death_cause is DeathCause.OLD_AGE


def test_ageing_advances_the_life_stage(world: World) -> None:
    agent = world.living_agents()[0]
    agent.age = balance.ELDER_FROM - 0.001

    LifecycleSystem().step(world, world.clock.day_seconds / balance.AGE_YEARS_PER_DAY)

    assert agent.age > balance.ELDER_FROM
    assert agent.life_stage is LifeStage.ELDER


def test_life_stage_thresholds() -> None:
    assert life_stage_for(5.0) is LifeStage.CHILD
    assert life_stage_for(balance.CHILD_UNTIL) is LifeStage.ADULT
    assert life_stage_for(balance.ELDER_FROM) is LifeStage.ELDER
