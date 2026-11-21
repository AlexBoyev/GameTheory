"""The world: terrain, entity registries and per-stream RNGs."""

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from app.core.world_config import WorldConfig
from app.sim import balance
from app.sim.clock import SimClock, season_offset_for
from app.sim.entities import Agent, Biome, ResourceNode, Shelter, Tribe
from app.sim.events import EventBus
from app.sim.rng import spawn_generators
from app.sim.spatial_hash import SpatialHash

RNG_STREAMS: tuple[str, ...] = ("worldgen", "spawn", "decide", "encounter", "action", "gossip")
"""Named RNG substreams; adding one never perturbs the others."""

INTERACTION_RADIUS: float = 4.0
"""Distance within which two agents may be drawn into an encounter."""

WATER_ORDINAL: int = list(Biome).index(Biome.WATER)


@dataclass(slots=True)
class Terrain:
    """Heightmap plus derived biome map, both `resolution x resolution`.

    Attributes:
        size: World extent in world units (the island spans -size/2..size/2).
        heights: Float32 heights in world units, row-major `[z][x]`.
        biomes: Uint8 `Biome` ordinals, same shape as `heights`.
        water_level: Height below which terrain is water.
    """

    size: float
    heights: np.ndarray
    biomes: np.ndarray
    water_level: float
    _flat_heights: list[float] | None = None
    _flat_biomes: bytes | None = None

    @property
    def resolution(self) -> int:
        """Grid cells per axis."""
        return int(self.heights.shape[0])

    @property
    def flat_heights(self) -> list[float]:
        """Row-major heights as Python floats.

        Scalar indexing into a numpy array costs microseconds; movement and
        perception do it hundreds of thousands of times a second. A plain list
        is an order of magnitude faster for single-cell reads, so the numpy
        arrays stay authoritative (and get sent to the browser) while lookups
        go through these flattened copies.
        """
        if self._flat_heights is None:
            self._flat_heights = [float(value) for value in self.heights.ravel()]
        return self._flat_heights

    @property
    def flat_biomes(self) -> bytes:
        """Row-major biome ordinals as bytes, for fast scalar reads."""
        if self._flat_biomes is None:
            self._flat_biomes = bytes(self.biomes.astype("<u1", copy=False).ravel())
        return self._flat_biomes

    @property
    def half_size(self) -> float:
        """Half the world extent - the coordinate limit on each axis."""
        return self.size / 2.0

    def cell_of(self, x: float, z: float) -> tuple[int, int]:
        """Return the `(row, col)` cell containing world position `(x, z)`."""
        resolution = self.resolution
        step = self.size / (resolution - 1)
        col = min(resolution - 1, max(0, round((x + self.half_size) / step)))
        row = min(resolution - 1, max(0, round((z + self.half_size) / step)))
        return row, col

    def height_at(self, x: float, z: float) -> float:
        """Sample terrain height at world position `(x, z)` (nearest cell)."""
        row, col = self.cell_of(x, z)
        return self.flat_heights[row * self.resolution + col]

    def biome_at(self, x: float, z: float) -> int:
        """Return the biome ordinal at world position `(x, z)`."""
        row, col = self.cell_of(x, z)
        return self.flat_biomes[row * self.resolution + col]

    def is_water(self, x: float, z: float) -> bool:
        """True where `(x, z)` is sea or lake - agents cannot walk here."""
        return self.biome_at(x, z) == WATER_ORDINAL

    def is_walkable(self, x: float, z: float) -> bool:
        """True where `(x, z)` is inside the island and on land."""
        limit = self.half_size
        if not (-limit <= x <= limit and -limit <= z <= limit):
            return False
        resolution = self.resolution
        step = self.size / (resolution - 1)
        half = self.half_size
        col = min(resolution - 1, max(0, round((x + half) / step)))
        row = min(resolution - 1, max(0, round((z + half) / step)))
        return self.flat_biomes[row * resolution + col] != WATER_ORDINAL


@dataclass(slots=True)
class World:
    """Mutable simulation state owned exclusively by the engine thread."""

    config: WorldConfig
    clock: SimClock
    terrain: Terrain
    rngs: dict[str, np.random.Generator]
    events: EventBus = field(default_factory=EventBus)
    agents: dict[int, Agent] = field(default_factory=dict)
    resources: dict[int, ResourceNode] = field(default_factory=dict)
    tribes: dict[int, Tribe] = field(default_factory=dict)
    shelters: dict[int, Shelter] = field(default_factory=dict)
    # Both indices are sized to the vision radius, because the hottest query
    # in the simulation is "what can this agent see" - that then touches nine
    # cells instead of the hundred-odd a smaller cell would need. Encounter
    # queries (radius 4) stay cheap either way: a vision-sized cell holds very
    # few agents at these densities.
    agent_index: SpatialHash = field(
        default_factory=lambda: SpatialHash(cell_size=balance.VISION_RADIUS)
    )
    resource_index: SpatialHash = field(
        default_factory=lambda: SpatialHash(cell_size=balance.VISION_RADIUS)
    )
    next_agent_id: int = 0
    next_resource_id: int = 0
    next_tribe_id: int = 0
    next_shelter_id: int = 0
    uid: int = 0
    """Incremented per built world, so per-agent caches know to start over."""
    births: int = 0
    deaths: int = 0
    _living: list[Agent] | None = None
    _living_tick: int = -1

    @property
    def population(self) -> int:
        """Number of living agents."""
        return sum(1 for agent in self.agents.values() if agent.alive)

    @property
    def scarcity(self) -> float:
        """Resource-yield divisor, worse in winter (SPEC 3.2)."""
        winter_penalty = 1.6 if self.clock.season == "winter" else 1.0
        return self.config.scarcity * winter_penalty

    def living_agents(self) -> list[Agent]:
        """Living agents in stable id order - the canonical iteration order.

        Every system iterates in this order. Dict insertion order would work
        today but would silently change the RNG stream the moment an agent is
        removed and another added, which is exactly what determinism forbids.

        Cached per tick: seven systems ask for this list every tick, and
        re-sorting a thousand agents seven times is pure waste. Anything that
        adds or removes an agent must call `invalidate_living()`.
        """
        if self._living is not None and self._living_tick == self.clock.tick:
            return self._living
        self._living = [agent for _, agent in sorted(self.agents.items()) if agent.alive]
        self._living_tick = self.clock.tick
        return self._living

    def invalidate_living(self) -> None:
        """Drop the cached living-agent list after a birth or a death."""
        self._living = None
        self._living_tick = -1

    def agent_at(self, agent_id: int) -> Agent | None:
        """Return the agent with `agent_id`, alive or not."""
        return self.agents.get(agent_id)


class WorldBuilder(Protocol):
    """Builds a fresh `World` from a `WorldConfig`. Deterministic per seed."""

    def build(self, config: WorldConfig) -> World:
        """Generate terrain, scatter resources and spawn the population."""
        ...


def empty_world(config: WorldConfig, terrain: Terrain | None = None) -> World:
    """Return a world with no entities, and flat terrain unless given some."""
    if terrain is None:
        resolution = config.terrain.resolution
        terrain = Terrain(
            size=config.terrain.size,
            heights=np.zeros((resolution, resolution), dtype=np.float32),
            biomes=np.zeros((resolution, resolution), dtype=np.uint8),
            water_level=config.terrain.water_level * config.terrain.max_height,
        )
    return World(
        config=config,
        clock=SimClock(season_offset=season_offset_for(config.season_start)),
        terrain=terrain,
        rngs=spawn_generators(config.seed, RNG_STREAMS),
    )
