"""World generation: an island, with resources where they belong."""

import math

import numpy as np
import pytest

from app.core.world_config import TerrainConfig, WorldConfig
from app.sim.entities import Biome, BrainType, ResourceKind, TribeRole
from app.sim.world import World
from app.sim.worldgen import IslandWorldBuilder
from app.sim.worldgen.grid import BIOME_ORDINALS, shore_cells
from tests.conftest import SMALL_TERRAIN

WATER = BIOME_ORDINALS[Biome.WATER]


def test_the_edges_are_water_and_the_middle_is_not(world: World) -> None:
    biomes = world.terrain.biomes

    assert biomes[0, :].max() == WATER, "north edge must be sea"
    assert biomes[-1, :].max() == WATER, "south edge must be sea"
    assert biomes[:, 0].max() == WATER, "west edge must be sea"
    assert biomes[:, -1].max() == WATER, "east edge must be sea"

    centre = world.terrain.resolution // 2
    assert biomes[centre, centre] != WATER, "the island needs a middle"


def test_heights_are_bounded_by_the_config(world: World) -> None:
    heights = world.terrain.heights
    max_height = world.config.terrain.max_height

    assert heights.min() >= 0.0
    assert heights.max() <= max_height + 1e-5
    assert heights.dtype == np.float32


def test_the_island_has_several_biomes(world: World) -> None:
    present = set(np.unique(world.terrain.biomes).tolist())

    assert WATER in present
    assert len(present) >= 3, f"expected a varied island, got {present}"


def test_every_resource_is_reachable_on_foot(world: World) -> None:
    """Nothing may be placed where an agent cannot stand.

    Drinking spots included: they sit on the bank, not offshore. A node in the
    water is unreachable, because movement refuses to walk into the sea.
    """
    assert world.resources, "a world with no resources is unplayable"

    for node in world.resources.values():
        assert world.terrain.is_walkable(*node.position), (
            f"{node.kind.value} at {node.position} is not standable"
        )


def test_drinking_spots_are_on_the_shore(world: World) -> None:
    water_nodes = [node for node in world.resources.values() if node.kind is ResourceKind.WATER]

    assert water_nodes, "agents must be able to drink"
    assert all(node.infinite for node in water_nodes)
    assert shore_cells(world.terrain).size > 0

    # Each spot must actually be beside water, not merely on land.
    step = world.terrain.size / (world.terrain.resolution - 1)
    for node in water_nodes:
        x, z = node.position
        neighbours = [
            world.terrain.is_water(x + step, z),
            world.terrain.is_water(x - step, z),
            world.terrain.is_water(x, z + step),
            world.terrain.is_water(x, z - step),
        ]
        assert any(neighbours), f"drinking spot at {node.position} has no water beside it"


def test_resources_start_full_and_are_indexed(world: World) -> None:
    for node in world.resources.values():
        assert node.amount == node.capacity

    assert len(world.resource_index) == len(world.resources)


def test_population_spawns_on_land_and_is_indexed(world: World) -> None:
    assert world.population == world.config.population

    for agent in world.living_agents():
        assert not world.terrain.is_water(*agent.position)
        assert agent.health == 100.0
        assert agent.alive

    assert len(world.agent_index) == world.population


def test_agents_get_distinct_names_and_a_strategy(world: World) -> None:
    agents = world.living_agents()
    names = {agent.name for agent in agents}

    assert len(names) == len(agents), "names must be unique"
    assert all(agent.strategy for agent in agents)


def test_llm_agents_are_taken_from_the_config() -> None:
    config = WorldConfig(seed=3, population=12, llm_agents=4, terrain=SMALL_TERRAIN)
    world = IslandWorldBuilder().build(config)

    llm_agents = [a for a in world.living_agents() if a.brain_type is BrainType.LLM]
    assert len(llm_agents) == 4


def test_scarcity_reduces_the_number_of_resources() -> None:
    builder = IslandWorldBuilder()
    generous = builder.build(
        WorldConfig(seed=11, population=5, scarcity=0.5, terrain=SMALL_TERRAIN)
    )
    harsh = builder.build(WorldConfig(seed=11, population=5, scarcity=3.0, terrain=SMALL_TERRAIN))

    assert len(harsh.resources) < len(generous.resources)


def test_a_bigger_resolution_still_produces_an_island() -> None:
    config = WorldConfig(
        seed=8,
        population=4,
        terrain=TerrainConfig(resolution=128, size=256.0),
    )
    world = IslandWorldBuilder().build(config)

    assert world.terrain.resolution == 128
    assert world.terrain.biomes[0, 0] == WATER
    assert world.population == 4


# ------------------------------------------- personality and starting tribes


def test_trait_bias_moves_the_mean_without_flattening_the_spread() -> None:
    """A dishonest world still has to contain the occasional honest agent.

    Clamping everyone to the bias would be easier and much worse: the whole
    point of Liars' Island is that an honest agent there is an interesting
    minority, not an impossibility.
    """
    import statistics

    config = WorldConfig(
        seed=11,
        population=300,
        max_agents=400,
        terrain=SMALL_TERRAIN,
        trait_bias={"honesty": 0.2},
    )
    agents = IslandWorldBuilder().build(config).living_agents()
    honesty = [agent.traits.honesty for agent in agents]

    assert statistics.mean(honesty) == pytest.approx(0.2, abs=0.05)
    assert statistics.stdev(honesty) > 0.1, "a distribution, not a constant"
    assert max(honesty) > 0.5, "somebody honest should still turn up"
    # An untouched trait stays centred.
    assert statistics.mean([agent.traits.loyalty for agent in agents]) == pytest.approx(
        0.5, abs=0.05
    )


def test_a_trait_bias_is_clamped_away_from_the_extremes() -> None:
    """A world of pure saints has nothing to show, so 0.0 is not honoured."""
    config = WorldConfig(
        seed=12,
        population=60,
        max_agents=80,
        terrain=SMALL_TERRAIN,
        trait_bias={"aggression": 0.0},
    )
    agents = IslandWorldBuilder().build(config).living_agents()

    assert all(agent.traits.aggression >= 0.0 for agent in agents)
    assert max(agent.traits.aggression for agent in agents) > 0.0


def test_initial_tribes_are_formed_with_leaders_and_camps() -> None:
    config = WorldConfig(
        seed=13, population=80, max_agents=100, terrain=SMALL_TERRAIN, initial_tribes=4
    )

    world = IslandWorldBuilder().build(config)

    assert len(world.tribes) == 4
    for tribe in world.tribes.values():
        assert tribe.size >= 2
        assert tribe.leader_id in tribe.member_ids
        leader = world.agents[tribe.leader_id]
        assert leader.role is TribeRole.LEADER
        assert leader.tribe_id == tribe.id
    # Every member belongs to exactly one tribe.
    assigned = [agent for agent in world.living_agents() if agent.tribe_id is not None]
    assert len(assigned) == sum(tribe.size for tribe in world.tribes.values())


def test_initial_tribes_claim_different_ground() -> None:
    """Scattered membership would leave nothing to go to war over."""
    config = WorldConfig(
        seed=14, population=120, max_agents=150, terrain=SMALL_TERRAIN, initial_tribes=3
    )

    camps = [tribe.camp_position for tribe in IslandWorldBuilder().build(config).tribes.values()]

    assert len(camps) == 3
    distances = [
        math.dist(first, second)
        for index, first in enumerate(camps)
        for second in camps[index + 1 :]
    ]
    assert min(distances) > 1.0, "two tribes camped on the same spot"


def test_a_world_with_no_initial_tribes_starts_tribeless() -> None:
    config = WorldConfig(seed=15, population=40, max_agents=60, terrain=SMALL_TERRAIN)

    world = IslandWorldBuilder().build(config)

    assert world.tribes == {}
    assert all(agent.tribe_id is None for agent in world.living_agents())


def test_initial_tribes_are_deterministic() -> None:
    config = WorldConfig(
        seed=16, population=60, max_agents=80, terrain=SMALL_TERRAIN, initial_tribes=3
    )

    first = IslandWorldBuilder().build(config)
    second = IslandWorldBuilder().build(config)

    assert {tribe.id: sorted(tribe.member_ids) for tribe in first.tribes.values()} == {
        tribe.id: sorted(tribe.member_ids) for tribe in second.tribes.values()
    }


def test_too_few_agents_to_go_round_forms_no_tribes() -> None:
    """Four tribes out of three people is nobody's idea of a society."""
    config = WorldConfig(
        seed=17, population=3, max_agents=10, terrain=SMALL_TERRAIN, initial_tribes=4
    )

    assert IslandWorldBuilder().build(config).tribes == {}
