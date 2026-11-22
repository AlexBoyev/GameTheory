"""The tick pipeline: ordered systems operating on the `World`.

Order matters for determinism, so the pipeline is an explicit list rather than
a discovered set.
"""

from collections.abc import Callable
from typing import Protocol, TypeVar, runtime_checkable

from app.sim.world import World

_S = TypeVar("_S")


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
    """Runs systems in a fixed order, once per tick.

    A pipeline may hold a second, alternative set for a world that asks for
    one: a tournament world runs no needs decay, no skills and no lifecycle
    (SPEC 5.3), and the engine rebuilds the *world* on reset but keeps the
    pipeline it was constructed with. Choosing per world rather than per
    construction is what lets you switch to the Axelrod preset at runtime and
    actually get a tournament instead of a ring of starving contestants.
    """

    __slots__ = ("_alternative", "_chooses", "_systems")

    def __init__(
        self,
        systems: tuple[System, ...] = (),
        alternative: tuple[System, ...] | None = None,
        chooses: Callable[[World], bool] | None = None,
    ) -> None:
        self._systems = systems
        self._alternative = alternative
        self._chooses = chooses

    def for_world(self, world: World) -> tuple[System, ...]:
        """The systems this world should run."""
        if self._alternative is not None and self._chooses is not None and self._chooses(world):
            return self._alternative
        return self._systems

    @property
    def systems(self) -> tuple[System, ...]:
        """The default systems, in running order."""
        return self._systems

    @property
    def names(self) -> tuple[str, ...]:
        """Names of the default systems, in running order."""
        return tuple(system.name for system in self._systems)

    def find(self, name: str) -> System | None:
        """Return the system called `name` from either set, or `None`."""
        for system in (*self._systems, *(self._alternative or ())):
            if system.name == name:
                return system
        return None

    def require(self, name: str, kind: type[_S]) -> _S:
        """Return the system called `name`, asserting its type.

        Used by the composition root to hand a specific system to the service
        layer (the tournament's standings, say) without `build_pipeline`
        having to return a tuple for every caller's benefit.
        """
        found = self.find(name)
        if not isinstance(found, kind):
            msg = f"pipeline has no {kind.__name__} called {name!r}"
            raise LookupError(msg)
        return found

    def step(self, world: World, dt: float) -> None:
        """Run every system once."""
        for system in self.for_world(world):
            system.step(world, dt)

    def on_world_replaced(self, world: World) -> None:
        """Notify systems that keep per-world caches that the world changed."""
        for system in {*self._systems, *(self._alternative or ())}:
            if isinstance(system, WorldAware):
                system.on_world_replaced(world)
