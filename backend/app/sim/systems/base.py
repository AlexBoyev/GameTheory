"""The tick pipeline: ordered systems operating on the `World`.

Order matters for determinism, so the pipeline is an explicit list rather than
a discovered set.
"""

from typing import Protocol, runtime_checkable

from app.sim.world import World


@runtime_checkable
class System(Protocol):
    """One stage of a tick.

    Implementations must be deterministic: no wall clock, no global RNG - draw
    from `world.rngs[<stream>]` instead, and iterate `world.living_agents()`
    rather than a dict.
    """

    name: str

    def step(self, world: World, dt: float) -> None:
        """Advance this system by `dt` sim-seconds."""
        ...


@runtime_checkable
class WorldAware(Protocol):
    """A system that caches per-world state and must be told about a reset."""

    def on_world_replaced(self, world: World) -> None:
        """Drop any cached state; `world` is the new one."""
        ...


class SystemPipeline:
    """Runs systems in a fixed order, once per tick."""

    __slots__ = ("_systems",)

    def __init__(self, systems: tuple[System, ...] = ()) -> None:
        self._systems = systems

    @property
    def systems(self) -> tuple[System, ...]:
        """The configured systems, in running order."""
        return self._systems

    @property
    def names(self) -> tuple[str, ...]:
        """Names of the configured systems, in running order."""
        return tuple(system.name for system in self._systems)

    def step(self, world: World, dt: float) -> None:
        """Run every system once."""
        for system in self._systems:
            system.step(world, dt)

    def on_world_replaced(self, world: World) -> None:
        """Notify systems that keep per-world caches that the world changed."""
        for system in self._systems:
            if isinstance(system, WorldAware):
                system.on_world_replaced(world)
