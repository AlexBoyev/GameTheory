"""`IslandWorldBuilder` - terrain, then resources, then people."""

from app.core.world_config import WorldConfig
from app.sim.clock import SimClock, season_offset_for
from app.sim.world import World, empty_world
from app.sim.worldgen.population import spawn_population
from app.sim.worldgen.resources import scatter_resources
from app.sim.worldgen.terrain import generate_terrain


class IslandWorldBuilder:
    """Builds the island. Deterministic for a given `WorldConfig`.

    The only state it carries is a build counter, which stamps each world with
    a `uid` so per-agent caches in the AI layer know when to start over.
    """

    __slots__ = ("_builds",)

    def __init__(self) -> None:
        self._builds = 0

    @property
    def builds(self) -> int:
        """How many worlds this builder has produced."""
        return self._builds

    def build(self, config: WorldConfig) -> World:
        """Generate a complete world from `config`."""
        terrain = generate_terrain(config.terrain, config.seed)
        world = empty_world(config, terrain)
        world.clock = SimClock(
            dt=config.dt,
            day_seconds=config.day_seconds,
            days_per_season=config.days_per_season,
            season_offset=season_offset_for(config.season_start),
        )
        self._builds += 1
        world.uid = self._builds
        scatter_resources(world, config)
        spawn_population(world, config)
        return world
