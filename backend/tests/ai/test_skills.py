"""Every skill's preconditions and effects (CLAUDE.md rule 6).

Each skill gets: what stops it running, and what changes when it does.
"""

import numpy as np
import pytest

from app.ai.skills.base import SkillCategory, SkillStatus
from app.ai.skills.hunting import HuntParams, HuntRabbit
from app.ai.skills.movement import Flee, FleeParams, MoveTo, MoveToParams, Wander
from app.ai.skills.registry import build_registry
from app.ai.skills.sustenance import Drink, Eat, Gather, Sleep
from app.core.result import is_ok
from app.sim import balance
from app.sim.entities import ResourceKind, Traits
from app.sim.world import World
from tests.factories import centre_agent, clear_resources, place, run_until_done

EXPECTED_SKILLS = {
    "Wander",
    "MoveTo",
    "Gather",
    "Eat",
    "Drink",
    "Sleep",
    "HuntRabbit",
    "Flee",
}


# ------------------------------------------------------------------- registry


def test_the_registry_discovers_exactly_the_phase_2_skills() -> None:
    registry = build_registry()

    assert set(registry.names) == EXPECTED_SKILLS
    assert all(type(skill).category is SkillCategory.SURVIVAL for skill in registry.all())


def test_every_skill_exposes_a_json_schema_for_the_llm() -> None:
    for skill in build_registry().all():
        described = type(skill).describe()
        assert described["name"]
        assert described["description"]
        assert "properties" in described["params"] or described["params"]["type"] == "object"


# --------------------------------------------------------------------- Wander


def test_wander_is_always_available_and_moves_the_agent(world: World) -> None:
    agent = centre_agent(world)
    skill = Wander()

    assert is_ok(skill.check(agent, world, Wander.Params()))

    run = skill.start(agent, world, Wander.Params())
    assert skill.step(run, world, 0.1) is SkillStatus.RUNNING
    assert agent.velocity != (0.0, 0.0)


def test_wander_finishes_after_its_duration(world: World) -> None:
    agent = centre_agent(world)
    skill = Wander()
    run = skill.start(agent, world, Wander.Params())

    status = skill.step(run, world, balance.WANDER_MAX_DURATION + 1.0)

    assert status is SkillStatus.DONE
    assert agent.velocity == (0.0, 0.0)


def test_wander_scores_below_any_real_need(world: World) -> None:
    from app.ai.brains.base import DecisionContext
    from app.ai.memory import AgentMemory

    agent = centre_agent(world)
    agent.needs.hunger = 10.0
    agent.inventory.food = 2.0
    ctx = DecisionContext(agent=agent, world=world, memory=AgentMemory())

    assert Wander().utility(agent, ctx) < Eat().utility(agent, ctx)


# --------------------------------------------------------------------- MoveTo


def test_move_to_is_not_offered_to_the_utility_brain() -> None:
    assert MoveTo.autonomous is False


def test_move_to_rejects_water_and_accepts_land(world: World) -> None:
    agent = centre_agent(world)
    skill = MoveTo()
    half = world.terrain.half_size

    assert is_ok(skill.check(agent, world, MoveToParams(x=0.0, z=0.0)))
    assert not is_ok(skill.check(agent, world, MoveToParams(x=half, z=half)))


def test_move_to_arrives(world: World) -> None:
    agent = centre_agent(world)

    status = run_until_done(MoveTo(), world, agent, MoveToParams(x=4.0, z=0.0))

    assert status is SkillStatus.DONE
    assert abs(agent.position[0] - 4.0) <= balance.ARRIVAL_DISTANCE


# ----------------------------------------------------------------------- Eat


def test_eat_needs_food_and_an_appetite(world: World) -> None:
    agent = centre_agent(world)
    skill = Eat()

    agent.inventory.food = 0.0
    agent.needs.hunger = 10.0
    assert not is_ok(skill.check(agent, world, Eat.Params()))

    agent.inventory.food = 1.0
    agent.needs.hunger = 99.0
    assert not is_ok(skill.check(agent, world, Eat.Params()))

    agent.needs.hunger = 40.0
    assert is_ok(skill.check(agent, world, Eat.Params()))


def test_eating_converts_food_into_hunger_relief(world: World) -> None:
    agent = centre_agent(world)
    agent.inventory.food = 3.0
    agent.needs.hunger = 20.0

    status = run_until_done(Eat(), world, agent, Eat.Params())

    assert status is SkillStatus.DONE
    assert agent.inventory.food == pytest.approx(2.0)
    assert agent.needs.hunger > 20.0


# -------------------------------------------------------------------- Gather


def test_gather_needs_food_in_sight_and_room_to_carry(world: World) -> None:
    agent = centre_agent(world)
    skill = Gather()
    clear_resources(world)

    assert not is_ok(skill.check(agent, world, Gather.Params()))

    place(world, ResourceKind.BERRY_BUSH, (1.0, 0.0))
    assert is_ok(skill.check(agent, world, Gather.Params()))

    agent.inventory.food = balance.CARRY_TARGET
    assert not is_ok(skill.check(agent, world, Gather.Params()))


def test_gathering_moves_food_from_the_bush_to_the_inventory(world: World) -> None:
    agent = centre_agent(world)
    clear_resources(world)
    bush = place(world, ResourceKind.BERRY_BUSH, (0.5, 0.0))

    status = run_until_done(Gather(), world, agent, Gather.Params())

    assert status is SkillStatus.DONE
    assert agent.inventory.food > 0.0
    assert bush.amount < bush.capacity


def test_gather_fails_when_its_target_vanishes(world: World) -> None:
    agent = centre_agent(world)
    clear_resources(world)
    bush = place(world, ResourceKind.BERRY_BUSH, (0.5, 0.0))
    skill = Gather()
    run = skill.start(agent, world, Gather.Params())

    del world.resources[bush.id]

    assert skill.step(run, world, 0.1) is SkillStatus.FAILED


# --------------------------------------------------------------------- Drink


def test_drink_needs_thirst_and_water(world: World) -> None:
    agent = centre_agent(world)
    skill = Drink()
    clear_resources(world)

    agent.needs.thirst = 50.0
    assert not is_ok(skill.check(agent, world, Drink.Params()))

    place(world, ResourceKind.WATER, (1.0, 0.0))
    assert is_ok(skill.check(agent, world, Drink.Params()))

    agent.needs.thirst = 100.0
    assert not is_ok(skill.check(agent, world, Drink.Params()))


def test_drinking_fills_thirst(world: World) -> None:
    agent = centre_agent(world)
    clear_resources(world)
    place(world, ResourceKind.WATER, (0.5, 0.0))
    agent.needs.thirst = 30.0

    status = run_until_done(Drink(), world, agent, Drink.Params())

    assert status is SkillStatus.DONE
    assert agent.needs.thirst >= 99.0


# --------------------------------------------------------------------- Sleep


def test_sleep_needs_tiredness_and_restores_energy(world: World) -> None:
    agent = centre_agent(world)
    skill = Sleep()

    agent.needs.energy = 100.0
    assert not is_ok(skill.check(agent, world, Sleep.Params()))

    agent.needs.energy = 40.0
    assert is_ok(skill.check(agent, world, Sleep.Params()))

    status = run_until_done(skill, world, agent, Sleep.Params())
    assert status is SkillStatus.DONE
    assert agent.needs.energy >= 99.0


# ----------------------------------------------------------------- HuntRabbit


def test_hunting_needs_a_rabbit_and_some_energy(world: World) -> None:
    agent = centre_agent(world)
    skill = HuntRabbit()
    clear_resources(world)

    assert not is_ok(skill.check(agent, world, HuntParams()))

    place(world, ResourceKind.RABBIT, (1.0, 0.0))
    assert is_ok(skill.check(agent, world, HuntParams()))

    agent.needs.energy = 5.0
    assert not is_ok(skill.check(agent, world, HuntParams()))


def test_catch_chance_rewards_courage_and_stamina(world: World) -> None:
    agent = centre_agent(world)
    agent.traits = Traits(courage=1.0)
    agent.needs.energy = 100.0
    brave = HuntRabbit._catch_chance(agent)

    agent.traits = Traits(courage=0.0)
    timid = HuntRabbit._catch_chance(agent)

    assert brave > timid
    assert 0.0 < timid <= brave <= 1.0


def test_a_successful_catch_feeds_the_hunter_and_emits_an_event(world: World) -> None:
    agent = centre_agent(world)
    clear_resources(world)
    rabbit = place(world, ResourceKind.RABBIT, (0.5, 0.0))
    agent.inventory.food = 0.0

    status = HuntRabbit._catch(world, agent, rabbit_id=rabbit.id)

    assert status is SkillStatus.DONE
    assert agent.inventory.food == pytest.approx(balance.RABBIT_FOOD)
    assert rabbit.depleted
    assert any(event.type.value == "hunt" for event in world.events.drain())


def test_a_hunt_always_terminates(world: World) -> None:
    agent = centre_agent(world)
    agent.traits = Traits(courage=0.5)
    clear_resources(world)
    place(world, ResourceKind.RABBIT, (0.5, 0.0))
    world.rngs["action"] = np.random.default_rng(12345)

    status = run_until_done(HuntRabbit(), world, agent, HuntParams())

    assert status in {SkillStatus.DONE, SkillStatus.FAILED}


# ---------------------------------------------------------------------- Flee


def test_flee_needs_something_to_run_from(world: World) -> None:
    agent = centre_agent(world)
    skill = Flee()

    assert not is_ok(skill.check(agent, world, FleeParams()))

    bully = world.living_agents()[1]
    bully.traits = Traits(aggression=1.0)
    bully.position = (2.0, 0.0)
    world.agent_index.insert(bully.id, 2.0, 0.0)

    assert is_ok(skill.check(agent, world, FleeParams()))


def test_fleeing_moves_away_from_the_threat_and_costs_safety(world: World) -> None:
    agent = centre_agent(world)
    bully = world.living_agents()[1]
    bully.traits = Traits(aggression=1.0)
    bully.position = (2.0, 0.0)
    world.agent_index.insert(bully.id, 2.0, 0.0)
    agent.needs.safety = 100.0

    skill = Flee()
    run = skill.start(agent, world, FleeParams())
    skill.step(run, world, 0.1)

    assert agent.velocity[0] < 0.0, "must run away from a threat on the +x side"
    assert agent.needs.safety < 100.0


def test_flee_ends_when_the_threat_is_gone(world: World) -> None:
    agent = centre_agent(world)
    bully = world.living_agents()[1]
    bully.traits = Traits(aggression=1.0)
    bully.position = (2.0, 0.0)
    world.agent_index.insert(bully.id, 2.0, 0.0)

    skill = Flee()
    run = skill.start(agent, world, FleeParams())
    bully.alive = False

    assert skill.step(run, world, 0.1) is SkillStatus.DONE
