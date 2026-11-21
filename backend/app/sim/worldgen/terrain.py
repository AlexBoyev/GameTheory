"""Island heightmap and biome map from seeded OpenSimplex noise (SPEC 3).

Shape of the recipe: fractal noise for the lumps, a radial falloff so the land
ends in water rather than at the edge of the array, and a second noise field
that carves inland lakes. Biomes then fall out of height plus moisture.
"""

import numpy as np
from opensimplex import OpenSimplex

from app.core.world_config import TerrainConfig
from app.sim.entities import Biome
from app.sim.world import Terrain

LAKE_THRESHOLD = 0.68
"""Lake noise above this carves water into otherwise dry land."""

LAKE_DEPTH = 0.86
"""Lake floors sit at this fraction of the water level."""

MOISTURE_FOREST = 0.45
"""Moisture above this turns mid-altitude meadow into forest."""

_BIOME_ORDINALS: dict[Biome, int] = {biome: index for index, biome in enumerate(Biome)}


NOISE_DOWNSCALE = 2
"""Noise is sampled at `resolution / 2` and upsampled.

`opensimplex` has no JIT here, so each octave over a 128x128 grid costs about
250 ms - eleven of those is a three-second pause every time you press reset.
Halving the sample grid is a 4x saving per octave and costs nothing visible:
the island is deliberately smooth, and the mesh is smooth-shaded anyway.
"""

MIN_NOISE_RESOLUTION = 32


def _bilinear_upsample(field: np.ndarray, target: int) -> np.ndarray:
    """Resample a square field up to `target x target`, bilinearly."""
    source = field.shape[0]
    if source == target:
        return field

    coordinates = np.linspace(0.0, source - 1.0, target)
    low = np.floor(coordinates).astype(np.int64)
    high = np.minimum(low + 1, source - 1)
    weight = coordinates - low

    rows_low = field[low]
    rows_high = field[high]
    weight_x = weight[None, :]
    top = rows_low[:, low] * (1.0 - weight_x) + rows_low[:, high] * weight_x
    bottom = rows_high[:, low] * (1.0 - weight_x) + rows_high[:, high] * weight_x
    weight_y = weight[:, None]
    blended: np.ndarray = top * (1.0 - weight_y) + bottom * weight_y
    return blended


def _fbm(simplex: OpenSimplex, resolution: int, span: float, octaves: int) -> np.ndarray:
    """Return fractal noise in `[0, 1]`, shaped `(resolution, resolution)`."""
    samples = max(MIN_NOISE_RESOLUTION, resolution // NOISE_DOWNSCALE)
    coordinates = np.linspace(0.0, span, samples, dtype=np.float64)

    total = np.zeros((samples, samples), dtype=np.float64)
    amplitude = 1.0
    frequency = 1.0
    normalisation = 0.0
    for _ in range(octaves):
        scaled = coordinates * frequency
        total += simplex.noise2array(scaled, scaled) * amplitude
        normalisation += amplitude
        amplitude *= 0.5
        frequency *= 2.0

    normalised = (total / normalisation + 1.0) * 0.5
    return _bilinear_upsample(normalised, resolution)


def _radial_mask(resolution: int, falloff: float) -> np.ndarray:
    """Return a centre-to-edge mask in `[0, 1]`: 1 inland, 0 at the border."""
    axis = np.linspace(-1.0, 1.0, resolution, dtype=np.float64)
    grid_x, grid_z = np.meshgrid(axis, axis)
    distance = np.clip(np.hypot(grid_x, grid_z), 0.0, 1.0)
    return np.clip(1.0 - distance**falloff, 0.0, 1.0)


def classify_biomes(normalised: np.ndarray, moisture: np.ndarray, water_level: float) -> np.ndarray:
    """Return a uint8 biome map from normalised height and moisture."""
    biomes = np.full(normalised.shape, _BIOME_ORDINALS[Biome.MEADOW], dtype=np.uint8)
    land = normalised - water_level
    span = max(1e-6, 1.0 - water_level)
    relative = land / span

    biomes[normalised < water_level] = _BIOME_ORDINALS[Biome.WATER]
    biomes[(normalised >= water_level) & (relative < 0.08)] = _BIOME_ORDINALS[Biome.BEACH]
    meadow = (relative >= 0.08) & (relative < 0.45)
    biomes[meadow] = _BIOME_ORDINALS[Biome.MEADOW]
    biomes[meadow & (moisture > MOISTURE_FOREST)] = _BIOME_ORDINALS[Biome.FOREST]
    biomes[(relative >= 0.45) & (relative < 0.75)] = _BIOME_ORDINALS[Biome.HILLS]
    biomes[relative >= 0.75] = _BIOME_ORDINALS[Biome.PEAKS]
    return biomes


def generate_terrain(config: TerrainConfig, seed: int) -> Terrain:
    """Generate the island for `seed`.

    Uses three independent noise fields (shape, lakes, moisture) derived from
    the seed by fixed offsets, so adding a field later cannot shift the others.
    """
    resolution = config.resolution

    shape_noise = _fbm(OpenSimplex(seed=seed), resolution, 3.0, config.octaves)
    lake_noise = _fbm(OpenSimplex(seed=seed + 7919), resolution, 2.1, 2)
    moisture = _fbm(OpenSimplex(seed=seed + 104729), resolution, 1.5, 2)

    # Bias upwards before masking so the middle of the island is reliably land.
    normalised = np.clip(shape_noise * 0.85 + 0.25, 0.0, 1.0)
    normalised *= _radial_mask(resolution, config.falloff)

    inland_lake = (lake_noise > LAKE_THRESHOLD) & (normalised > config.water_level + 0.05)
    normalised[inland_lake] = config.water_level * LAKE_DEPTH

    biomes = classify_biomes(normalised, moisture, config.water_level)
    heights = (normalised * config.max_height).astype(np.float32)

    return Terrain(
        size=config.size,
        heights=heights,
        biomes=biomes,
        water_level=config.water_level * config.max_height,
    )


def biome_names() -> list[str]:
    """Return biome names ordered by their wire ordinal."""
    return [biome.value for biome in Biome]
