"""Simulation time: ticks, sim-seconds, days and seasons (SPEC section 2.2)."""

from dataclasses import dataclass, replace
from typing import Final

from app.core.world_config import Season

SEASONS: Final[tuple[Season, ...]] = ("spring", "summer", "autumn", "winter")

SPEED_PRESETS: Final[tuple[float, ...]] = (0.0, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, -1.0)
"""Index 0 = pause, index 7 (-1.0) = MAX (as fast as the CPU allows)."""

MAX_SPEED: Final[float] = -1.0


@dataclass(frozen=True, slots=True)
class SimClock:
    """Immutable simulation clock; `advance()` returns the next clock.

    Attributes:
        tick: Number of elapsed fixed timesteps.
        dt: Sim-seconds per tick.
        day_seconds: Sim-seconds in one day.
        days_per_season: Days in one season.
        season_offset: Index into `SEASONS` the world started at.
    """

    tick: int = 0
    dt: float = 0.1
    day_seconds: float = 240.0
    days_per_season: int = 7
    season_offset: int = 0

    @property
    def sim_seconds(self) -> float:
        """Total elapsed sim-seconds."""
        return self.tick * self.dt

    @property
    def day(self) -> int:
        """Zero-based day index."""
        return int(self.sim_seconds // self.day_seconds)

    @property
    def time_of_day(self) -> float:
        """Position within the current day in `[0, 1)` (0.0 = midnight)."""
        return (self.sim_seconds % self.day_seconds) / self.day_seconds

    @property
    def is_night(self) -> bool:
        """True between 20:00 and 06:00 sim-time."""
        return self.time_of_day < 0.25 or self.time_of_day >= 0.83

    @property
    def season_index(self) -> int:
        """Index into `SEASONS` for the current day."""
        return (self.season_offset + self.day // self.days_per_season) % len(SEASONS)

    @property
    def season(self) -> Season:
        """Current season."""
        return SEASONS[self.season_index]

    @property
    def year(self) -> int:
        """Zero-based year index."""
        return self.day // (self.days_per_season * len(SEASONS))

    def advance(self, ticks: int = 1) -> "SimClock":
        """Return a clock advanced by `ticks` fixed timesteps."""
        if ticks < 0:
            msg = "the simulation clock never runs backwards"
            raise ValueError(msg)
        return replace(self, tick=self.tick + ticks)


def season_offset_for(season: Season) -> int:
    """Return the `SEASONS` index for `season`."""
    return SEASONS.index(season)
