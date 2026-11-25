"""What the world looks like at the moment a day turns.

Its own module so the headline rules and the chronicle can both see it
without importing each other.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DayFacts:
    """The state of the world at the moment a day turns."""

    day: int
    """The day now beginning, zero-based like `SimClock.day`."""

    season: str
    population: int
    tribes: int
    tribes_at_war: int
    deaths_by_cause: Mapping[str, int] = field(default_factory=dict)
    """Cumulative totals from the world, not a count of events.

    The feed is a bounded queue that drops batches when a client is slow, so
    counting `death` events undercounts exactly when the island is busiest -
    which is when the number matters. The world's own tally cannot drop one,
    and it carries the cause, which the wire form of an event does not.
    """
