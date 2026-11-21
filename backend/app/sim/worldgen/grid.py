"""Grid helpers shared by resource scattering and population spawning.

Cells are addressed as flat indices into the `resolution x resolution` biome
map, which makes "pick 40 random forest cells" a single vectorised draw.
"""

import numpy as np

from app.sim.entities import Biome
from app.sim.world import Terrain

BIOME_ORDINALS: dict[Biome, int] = {biome: index for index, biome in enumerate(Biome)}


def cells_in_biomes(terrain: Terrain, biomes: tuple[Biome, ...]) -> np.ndarray:
    """Return sorted flat indices of cells whose biome is one of `biomes`."""
    wanted = [BIOME_ORDINALS[biome] for biome in biomes]
    mask = np.isin(terrain.biomes, wanted)
    return np.flatnonzero(mask.ravel())


def land_cells(terrain: Terrain) -> np.ndarray:
    """Return sorted flat indices of every non-water cell."""
    return np.flatnonzero((terrain.biomes != BIOME_ORDINALS[Biome.WATER]).ravel())


def shore_cells(terrain: Terrain) -> np.ndarray:
    """Return **land** cells that touch water - where an agent stands to drink.

    Deliberately the dry side of the shoreline. A drinking spot placed in the
    water is unreachable, because movement refuses to walk into the sea: the
    agent approaches the bank, never gets within arrival distance of a node
    that sits offshore, and dies of thirst next to a lake.
    """
    water = terrain.biomes == BIOME_ORDINALS[Biome.WATER]
    land = ~water
    neighbour_water = np.zeros_like(water)
    neighbour_water[1:, :] |= water[:-1, :]
    neighbour_water[:-1, :] |= water[1:, :]
    neighbour_water[:, 1:] |= water[:, :-1]
    neighbour_water[:, :-1] |= water[:, 1:]
    return np.flatnonzero((land & neighbour_water).ravel())


def choose_cells(rng: np.random.Generator, cells: np.ndarray, count: int) -> np.ndarray:
    """Pick `count` cells, without replacement where possible."""
    if cells.size == 0 or count <= 0:
        return np.empty(0, dtype=np.int64)
    if count >= cells.size:
        return cells
    chosen: np.ndarray = rng.choice(cells, size=count, replace=False)
    return np.sort(chosen)


def cell_centre(terrain: Terrain, flat_index: int) -> tuple[float, float]:
    """Return the world `(x, z)` at the centre of a flat cell index."""
    resolution = terrain.resolution
    row, col = divmod(int(flat_index), resolution)
    step = terrain.size / (resolution - 1)
    half = terrain.size / 2.0
    return col * step - half, row * step - half


def jittered_positions(
    terrain: Terrain,
    cells: np.ndarray,
    rng: np.random.Generator,
    spread: float = 0.35,
) -> list[tuple[float, float]]:
    """Return one position per cell, nudged inside the cell for a natural look.

    `spread` is a fraction of the cell size; keep it small for anything that
    must stay strictly inside its own cell, such as a shoreline drinking spot.
    """
    if cells.size == 0:
        return []
    step = terrain.size / (terrain.resolution - 1)
    offsets = rng.uniform(-spread, spread, size=(cells.size, 2)) * step
    positions: list[tuple[float, float]] = []
    for index, flat_index in enumerate(cells):
        x, z = cell_centre(terrain, int(flat_index))
        positions.append((x + float(offsets[index, 0]), z + float(offsets[index, 1])))
    return positions
