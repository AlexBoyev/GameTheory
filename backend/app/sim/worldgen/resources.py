"""Scattering berries, trees, animals, stone and drinking spots (SPEC 3.1)."""

from dataclasses import dataclass

from app.core.world_config import WorldConfig
from app.sim import balance
from app.sim.entities import Biome, ResourceKind, ResourceNode
from app.sim.world import World
from app.sim.worldgen.grid import (
    cells_in_biomes,
    choose_cells,
    jittered_positions,
    land_cells,
    shore_cells,
)

MAX_WATER_NODES = 96
"""Drinking spots along the shoreline.

Thirst is the fastest-acting need, and an agent only drinks at a spot it can
see (18 units), so these have to be common enough that most of the coast is
covered - too few and inland agents die of thirst beside a visible lake.
"""

SHORE_JITTER = 0.15
"""Keep drinking spots well inside their land cell, away from the water."""


@dataclass(frozen=True, slots=True)
class ResourceRecipe:
    """How one resource kind is distributed and how it regrows."""

    kind: ResourceKind
    biomes: tuple[Biome, ...]
    share: float
    capacity: float
    regrowth: float


RECIPES: tuple[ResourceRecipe, ...] = (
    ResourceRecipe(
        kind=ResourceKind.BERRY_BUSH,
        biomes=(Biome.MEADOW, Biome.FOREST),
        share=0.42,
        capacity=balance.BERRY_CAPACITY,
        regrowth=balance.BERRY_REGROWTH,
    ),
    ResourceRecipe(
        kind=ResourceKind.TREE,
        biomes=(Biome.FOREST, Biome.HILLS),
        share=0.28,
        capacity=balance.TREE_CAPACITY,
        regrowth=balance.TREE_REGROWTH,
    ),
    ResourceRecipe(
        kind=ResourceKind.RABBIT,
        biomes=(Biome.MEADOW, Biome.BEACH),
        share=0.16,
        capacity=balance.RABBIT_CAPACITY,
        regrowth=balance.RABBIT_REGROWTH,
    ),
    ResourceRecipe(
        kind=ResourceKind.DEER,
        biomes=(Biome.FOREST, Biome.HILLS),
        share=0.07,
        capacity=balance.DEER_CAPACITY,
        regrowth=balance.DEER_REGROWTH,
    ),
    ResourceRecipe(
        kind=ResourceKind.STONE,
        biomes=(Biome.HILLS, Biome.PEAKS),
        share=0.07,
        capacity=balance.TREE_CAPACITY,
        regrowth=0.0,
    ),
)


def _total_nodes(world: World, config: WorldConfig) -> int:
    """Return how many nodes the island supports, scaled by scarcity."""
    terrain = world.terrain
    cell_area = (terrain.size / (terrain.resolution - 1)) ** 2
    land_area = float(land_cells(terrain).size) * cell_area
    return max(len(RECIPES), int(land_area * balance.RESOURCE_DENSITY / config.scarcity))


def scatter_resources(world: World, config: WorldConfig) -> None:
    """Fill `world.resources` deterministically from the worldgen RNG stream."""
    rng = world.rngs["worldgen"]
    terrain = world.terrain
    budget = _total_nodes(world, config)

    for recipe in RECIPES:
        candidates = cells_in_biomes(terrain, recipe.biomes)
        count = int(budget * recipe.share)
        cells = choose_cells(rng, candidates, count)
        for position in jittered_positions(terrain, cells, rng):
            _add_node(
                world,
                kind=recipe.kind,
                position=position,
                capacity=recipe.capacity,
                regrowth=recipe.regrowth,
            )

    water = choose_cells(rng, shore_cells(terrain), MAX_WATER_NODES)
    for position in jittered_positions(terrain, water, rng, spread=SHORE_JITTER):
        _add_node(
            world,
            kind=ResourceKind.WATER,
            position=position,
            capacity=1.0,
            regrowth=0.0,
            infinite=True,
        )

    world.resource_index.rebuild(
        (node.id, node.position[0], node.position[1])
        for node in sorted(world.resources.values(), key=lambda item: item.id)
    )


def _add_node(
    world: World,
    *,
    kind: ResourceKind,
    position: tuple[float, float],
    capacity: float,
    regrowth: float,
    infinite: bool = False,
) -> ResourceNode:
    """Create and register one resource node, starting full."""
    node = ResourceNode(
        id=world.next_resource_id,
        kind=kind,
        position=position,
        amount=capacity,
        capacity=capacity,
        regrowth_per_sim_s=regrowth,
        infinite=infinite,
    )
    world.resources[node.id] = node
    world.next_resource_id += 1
    return node


def add_corpse(world: World, position: tuple[float, float]) -> ResourceNode:
    """Leave a body behind as a short-lived food source (SPEC 4.2)."""
    return _add_node(
        world,
        kind=ResourceKind.CORPSE,
        position=position,
        capacity=balance.CORPSE_FOOD,
        regrowth=0.0,
    )
