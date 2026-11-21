"""Resource regrowth, winter scarcity, corpse decay and walking on land."""

import pytest

from app.sim import balance
from app.sim.clock import SimClock
from app.sim.entities import ResourceKind
from app.sim.systems import MovementSystem, RegrowthSystem
from app.sim.world import World
from app.sim.worldgen.resources import add_corpse


def _first_bush(world: World) -> int:
    for node_id in sorted(world.resources):
        if world.resources[node_id].kind is ResourceKind.BERRY_BUSH:
            return node_id
    pytest.skip("this world generated no berry bushes")


def test_harvested_bushes_regrow(world: World) -> None:
    bush = world.resources[_first_bush(world)]
    bush.amount = 0.0

    RegrowthSystem().step(world, 100.0)

    assert bush.amount > 0.0
    assert bush.amount <= bush.capacity


def test_regrowth_stops_in_winter(world: World) -> None:
    bush = world.resources[_first_bush(world)]
    bush.amount = 0.0
    world.clock = SimClock(dt=world.clock.dt, season_offset=3)
    assert world.clock.season == "winter"

    RegrowthSystem().step(world, 100.0)

    assert bush.amount == 0.0, "winter must stop berries regrowing (SPEC 3.2)"


def test_water_is_never_depleted(world: World) -> None:
    water = next(n for n in world.resources.values() if n.kind is ResourceKind.WATER)

    RegrowthSystem().step(world, 10.0)

    assert water.infinite
    assert not water.depleted


def test_corpses_rot_away_and_leave_the_index(world: World) -> None:
    corpse = add_corpse(world, (0.0, 0.0))
    world.resource_index.insert(corpse.id, 0.0, 0.0)

    RegrowthSystem().step(world, balance.CORPSE_DECAY_S + 1.0)

    assert corpse.id not in world.resources
    assert corpse.id not in world.resource_index


def test_movement_applies_velocity(world: World) -> None:
    agent = world.living_agents()[0]
    agent.position = (0.0, 0.0)
    agent.velocity = (2.0, 0.0)
    assert world.terrain.is_walkable(0.0, 0.0), "test assumes the centre is land"

    MovementSystem().step(world, 1.0)

    assert agent.position[0] == pytest.approx(2.0)
    assert agent.position[1] == pytest.approx(0.0)


def test_movement_refuses_to_walk_into_the_sea(world: World) -> None:
    agent = world.living_agents()[0]
    half = world.terrain.half_size
    agent.position = (0.0, 0.0)
    # Straight at the edge, which generation guarantees is water.
    agent.velocity = (half * 2, half * 2)

    MovementSystem().step(world, 1.0)

    assert world.terrain.is_walkable(*agent.position)


def test_movement_updates_the_spatial_index(world: World) -> None:
    agent = world.living_agents()[0]
    agent.position = (0.0, 0.0)
    agent.velocity = (1.0, 0.0)

    MovementSystem().step(world, 1.0)

    assert world.agent_index.position_of(agent.id) == agent.position


def test_standing_still_costs_nothing(world: World) -> None:
    agent = world.living_agents()[0]
    before = agent.position
    agent.velocity = (0.0, 0.0)

    MovementSystem().step(world, 1.0)

    assert agent.position == before
