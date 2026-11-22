"""Seeded world generation: terrain, resources, population (SPEC section 3).

Everything here is a pure function of `(WorldConfig.seed, WorldConfig)`, so
`IslandWorldBuilder().build(config)` twice gives two identical worlds.
"""

from app.sim.worldgen.builder import IslandWorldBuilder
from app.sim.worldgen.population import spawn_population
from app.sim.worldgen.resources import scatter_resources
from app.sim.worldgen.terrain import generate_terrain
from app.sim.worldgen.tribes import form_initial_tribes

__all__ = [
    "IslandWorldBuilder",
    "form_initial_tribes",
    "generate_terrain",
    "scatter_resources",
    "spawn_population",
]
