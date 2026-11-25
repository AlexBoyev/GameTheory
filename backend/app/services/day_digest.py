"""The day's chronicle: what was notable, for the card that announces the next.

A day is 2,400 ticks and the island is busier than it looks: measured on the
default world, roughly 156 fights, 625 rumours, a tribe or two and fifty huts
*per day*, almost none of it individually remarkable enough to notice in the
feed. Watching it live therefore reads as "nothing is happening" while a
society forms, which was the single most common thing said about this project.

So each time the clock turns over, this summarises the day that ended and
announces the one beginning. It is deliberately a *summary* and not a
prediction: the only honest thing to say about a day that has not happened
yet is what the calendar guarantees (a season, and what the season does).
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

WINTER_NOTE = "Winter: berry bushes stop regrowing until spring"
"""True by construction - `balance.WINTER_REGROWTH_FACTOR` is 0.0."""


@dataclass(frozen=True, slots=True)
class DayFacts:
    """The state of the world at the moment a day turns."""

    day: int
    """The day now beginning, zero-based like `SimClock.day`."""

    season: str
    population: int
    tribes: int
    tribes_at_war: int


@dataclass(frozen=True, slots=True)
class DayReport:
    """What the title card shows when a day begins."""

    day: int
    season: str
    headline: str
    """One line about the day that just ended, or how the world opened."""

    lines: tuple[str, ...]
    """Two to four supporting facts, already phrased for display."""

    counts: dict[str, int] = field(default_factory=dict)
    """Event tallies for the day that ended, for chips and for tests."""

    def as_dict(self) -> dict[str, Any]:
        """The wire form."""
        return {
            "day": self.day,
            "season": self.season,
            "headline": self.headline,
            "lines": list(self.lines),
            "counts": dict(self.counts),
        }


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """`1 war`, `3 wars` - with an irregular plural when one is given."""
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def _headline(counts: Counter[str], facts: DayFacts, deaths: int) -> str:
    """The one line worth leading with, in descending order of drama.

    Ordered rather than scored on purpose: a war is the story of its day even
    on a day with four hundred rumours, and a scoring function that can be
    out-shouted by volume would bury it.
    """
    if counts["war_declared"]:
        return f"War: {_plural(counts['war_declared'], 'declaration')} between tribes"
    if counts["coup"]:
        return f"{_plural(counts['coup'], 'chief')} overthrown"
    if counts["raid"] >= 3:
        return f"Raiding season: {_plural(counts['raid'], 'raid')}"
    if deaths >= 3:
        return f"{_plural(deaths, 'death')} on the island"
    if counts["tribe_founded"]:
        return f"{_plural(counts['tribe_founded'], 'new tribe')} founded"
    if counts["peace_made"]:
        return f"Peace: {_plural(counts['peace_made'], 'truce')} agreed"
    if counts["birth"]:
        return f"{_plural(counts['birth'], 'child')} born"
    if counts["shelter_built"] >= 3:
        return f"Building: {_plural(counts['shelter_built'], 'hut')} went up"
    if deaths:
        return f"{_plural(deaths, 'death')} on the island"
    return "A day of trading, gossip and small cruelties"


class DayChronicle:
    """Tallies events as they stream past and reports on each day turn.

    Fed from the broadcast feed's event hook, which runs on the event loop, so
    there is one writer and no locking. It holds counts for the current day
    only: the archive is what remembers history.
    """

    __slots__ = ("_counts", "_day", "_population", "_season")

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()
        self._day: int | None = None
        self._season: str | None = None
        self._population = 0

    def record(self, items: list[dict[str, Any]]) -> None:
        """Tally a batch of events from the feed."""
        for item in items:
            kind = item.get("type")
            if isinstance(kind, str):
                self._counts[kind] += 1

    def reset(self) -> None:
        """Forget everything: a new world is a new chronicle."""
        self._counts.clear()
        self._day = None
        self._season = None
        self._population = 0

    def seen(self, day: int) -> bool:
        """Whether `day` has already been reported.

        Asked on every frame - twenty times a second - so that reading the
        world for the report costs nothing on the other 99.9% of frames.
        """
        return self._day == day

    def turn(self, facts: DayFacts) -> DayReport | None:
        """Return the report for `facts.day`, or `None` if it is not new.

        The first call on a world establishes where we are and reports the
        opening, because "what am I watching" deserves an answer before the
        first day is over rather than after it.
        """
        if self._day == facts.day:
            return None

        first = self._day is None
        previous_season = self._season
        previous_population = self._population
        counts = Counter(self._counts)
        self._day, self._season, self._population = facts.day, facts.season, facts.population
        self._counts.clear()

        if first:
            return DayReport(
                day=facts.day,
                season=facts.season,
                headline=f"{facts.population} strangers wash up on an island",
                lines=(
                    "Nobody is related to anybody. Nobody owes anybody anything.",
                    "Every meeting from here is a game: share, trade, lie, or take.",
                    self._season_line(facts, changed=False),
                ),
                counts=dict(counts),
            )

        deaths = counts["death"]
        lines = [
            f"{_plural(counts['combat'], 'fight')}, "
            f"{_plural(counts['gossip'], 'rumour')}, "
            f"{_plural(counts['trade'] + counts['gift'], 'trade')}",
            f"{facts.population} alive ({facts.population - previous_population:+d} overnight)",
            f"{_plural(facts.tribes, 'tribe')}, {self._war_state(counts, facts)}",
        ]
        season_line = self._season_line(facts, changed=previous_season != facts.season)
        if season_line:
            lines.append(season_line)

        return DayReport(
            day=facts.day,
            season=facts.season,
            headline=_headline(counts, facts, deaths),
            lines=tuple(lines),
            counts=dict(counts),
        )

    @staticmethod
    def _war_state(counts: Counter[str], facts: DayFacts) -> str:
        """How the tribes stand now, in a way the headline cannot contradict.

        A card that led with "War: 1 declaration" and then said "none at
        war" read as a bug and was not one: the war was declared and settled
        inside the same day. Saying so is more interesting than either half.
        """
        if facts.tribes_at_war:
            return f"{facts.tribes_at_war} at war"
        if counts["peace_made"]:
            return f"{_plural(counts['peace_made'], 'truce')} ended the fighting"
        if counts["war_declared"]:
            return "the war is already over"
        return "none at war"

    @staticmethod
    def _season_line(facts: DayFacts, *, changed: bool) -> str:
        """What the calendar guarantees about the day beginning."""
        if facts.season == "winter":
            return f"{'Winter begins. ' if changed else ''}{WINTER_NOTE}"
        if changed:
            return f"{facts.season.capitalize()} begins"
        return ""
