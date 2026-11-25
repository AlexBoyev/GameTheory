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
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Notable:
    """An event type worth leading with, and how to say it."""

    kind: str
    singular: str
    plural: str | None = None
    floor: int = 3
    """Below this many in a day, a ratio is noise rather than news."""


NOTABLE: tuple[Notable, ...] = (
    Notable("killed", "killing", floor=3),
    Notable("starved", "death by hunger", "deaths by hunger", floor=3),
    Notable("war_declared", "war declared", "wars declared", floor=2),
    Notable("raid", "raid", floor=2),
    Notable("coup", "chief overthrown", "chiefs overthrown", floor=5),
    Notable("tribe_founded", "new tribe", floor=2),
    Notable("tribe_split", "tribe split apart", "tribes split apart", floor=1),
    Notable("tribe_left", "walked out of their tribe", floor=5),
    Notable("peace_made", "truce", floor=2),
    Notable("alliance", "alliance", floor=3),
    Notable("betrayal", "betrayal", floor=3),
    Notable("birth", "child born", "children born", floor=3),
    Notable("shelter_built", "hut went up", "huts went up", floor=3),
    Notable("combat", "fight", floor=20),
    Notable("gossip", "rumour", floor=100),
    Notable("lie_caught", "liar caught", "liars caught", floor=20),
    Notable("trade", "trade", floor=20),
    Notable("gift", "gift", floor=20),
)
"""What a day can be *about*, with the floor below which a spike is noise.

`killed` and `starved` are the day's deaths by cause, counted from the
world rather than from the feed and folded in here so they compete on the
same terms. They were absolute rules once and that was wrong in both
directions: deaths run at about three a day, so leading with them every day
is the monotony this rule exists to avoid, while leaving them out meant a
day with nine killings could be headlined by its alliances.

Ordered drama does not work on this island, which is the lesson of a live
run: coups looked like the second most dramatic thing that could happen, so
every card led with one - and coups turn out to run at 32 a day. Nearly
everything here happens every day. What makes a day worth announcing is
therefore not which events it contained but which of them it had *unusually
many of*, which is what `_spike` measures.
"""

SPIKE = 1.6
"""How far above its own running average a count has to be to lead."""

MIN_DAYS_FOR_AVERAGE = 2
"""Days of history before ratios mean anything. Until then, fixed rules."""

COHORT_DEATHS = 3
"""Old-age deaths in one day that mean the founding generation is going.

The island starts with everybody adult and nobody old, so they age together
and die together: measured on the default world, the first old-age death is
on day 8 and the population falls for the next ten days before the
survivors' children refill it. That turn is the most interesting thing that
happens in a run and it used to be reported as "9 deaths on the island".
"""

COLLAPSE_SURVIVORS = 10
"""At or below this, the story of the day is the collapse, whatever else
happened. A card reading "3 deaths on the island" when four people are left
is technically true and useless."""

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
    deaths_by_cause: Mapping[str, int] = field(default_factory=dict)
    """Cumulative totals from the world, not a count of events.

    The feed is a bounded queue that drops batches when a client is slow, so
    counting `death` events undercounts exactly when the island is busiest -
    which is when the number matters. The world's own tally cannot drop one,
    and it carries the cause, which the wire form of an event does not.
    """


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


def _multiple(ratio: float) -> str:
    """How a person would say "2.9 times as many"."""
    if ratio >= 4.0:
        return f"{ratio:.0f}x the usual"
    if ratio >= 2.6:
        return "triple the usual"
    if ratio >= 1.9:
        return "double the usual"
    return "well above the usual"


def _spike(counts: Counter[str], averages: Mapping[str, float]) -> str | None:
    """The day's biggest outlier against its own history, if it has one."""
    best: tuple[float, str] | None = None
    for notable in NOTABLE:
        count = counts[notable.kind]
        if count < notable.floor:
            continue
        average = averages.get(notable.kind, 0.0)
        ratio = count / average if average >= 1.0 else float("inf")
        if ratio < SPIKE:
            continue
        said = f"{_plural(count, notable.singular, notable.plural)}"
        phrase = said if ratio == float("inf") else f"{said} - {_multiple(ratio)}"
        score = 99.0 if ratio == float("inf") else ratio
        if best is None or score > best[0]:
            best = (score, phrase[0].upper() + phrase[1:])
    return None if best is None else best[1]


def _headline(
    counts: Counter[str],
    facts: DayFacts,
    deaths: Counter[str],
    averages: Mapping[str, float] | None = None,
) -> str:
    """The one line worth leading with.

    Deaths and collapse are absolute - a generation dying is the story of
    its day whatever else happened - and everything below that is relative,
    because on this island nearly everything happens every day. See
    `NOTABLE`.
    """
    total = sum(deaths.values())
    if facts.population == 0:
        return "The island is empty"
    if facts.population <= COLLAPSE_SURVIVORS:
        return f"The island is nearly empty: {_plural(facts.population, 'survivor')} left"
    if deaths["old_age"] >= COHORT_DEATHS:
        # The die-off lasts about ten days, and saying the same sentence ten
        # times is the monotony these rules exist to avoid. The first day is
        # the news; after that the running total is.
        so_far = facts.deaths_by_cause.get("old_age", deaths["old_age"])
        if so_far == deaths["old_age"]:
            return (
                "The founding generation is going: "
                f"{_plural(deaths['old_age'], 'death')} of old age"
            )
        return f"{deaths['old_age']} more founders gone - {so_far} of old age so far"
    if averages is not None:
        # With history, the question is only what was unusual. Falling
        # through to the fixed rules here is what made every card lead with
        # a coup: they fire on *any* count, and this island has coups daily.
        return _spike(counts, averages) or _ordinary_day(counts)

    # No history yet - the first two days of a world. Fixed order, and the
    # only place it is still right, because nothing has a usual yet.
    if counts["killed"] >= COHORT_DEATHS:
        return f"{_plural(counts['killed'], 'killing')} on the island"
    if counts["starved"] >= COHORT_DEATHS:
        return f"Hunger: {_plural(counts['starved'], 'death')}"
    if total >= 3:
        return f"{_plural(total, 'death')} on the island"
    if counts["war_declared"]:
        return f"War: {_plural(counts['war_declared'], 'declaration')} between tribes"
    if counts["coup"]:
        return f"{_plural(counts['coup'], 'chief')} overthrown"
    if counts["tribe_founded"]:
        return f"{_plural(counts['tribe_founded'], 'new tribe')} founded"
    if counts["peace_made"]:
        return f"Peace: {_plural(counts['peace_made'], 'truce')} agreed"
    if counts["birth"]:
        return f"{_plural(counts['birth'], 'child')} born"
    if counts["shelter_built"] >= 3:
        return f"Building: {_plural(counts['shelter_built'], 'hut')} went up"
    if total:
        return f"{_plural(total, 'death')} on the island"
    return _ordinary_day(counts)


def _ordinary_day(counts: Counter[str]) -> str:
    """What to say when nothing stood out - which is most days, and fine.

    Named after what it is: the island is busy every day, so "nothing
    unusual" still means several hundred encounters.
    """
    exchanges = counts["trade"] + counts["gift"] + counts["cooperation"]
    if exchanges and counts["combat"]:
        return "A day of trading, gossip and small cruelties"
    if exchanges:
        return "A quiet day of trading and gossip"
    return "A quiet day"


class DayChronicle:
    """Tallies events as they stream past and reports on each day turn.

    Fed from the broadcast feed's event hook, which runs on the event loop, so
    there is one writer and no locking. It holds counts for the current day
    only: the archive is what remembers history.
    """

    __slots__ = ("_counts", "_day", "_days", "_deaths", "_population", "_season", "_totals")

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()
        self._totals: Counter[str] = Counter()
        self._days = 0
        self._deaths: Counter[str] = Counter()
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
        self._totals.clear()
        self._days = 0
        self._deaths.clear()
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
        # Deaths come from the world's cumulative tally, so the day's figure
        # is the difference since the last turn (see `DayFacts`).
        cumulative = Counter(facts.deaths_by_cause)
        deaths = cumulative - self._deaths
        self._deaths = cumulative
        # Deaths compete for the headline on the same terms as everything
        # else, so they go into the same tally the averages are kept over.
        if deaths["combat"]:
            counts["killed"] = deaths["combat"]
        if deaths["starvation"]:
            counts["starved"] = deaths["starvation"]
        averages = (
            {kind: total / self._days for kind, total in self._totals.items()}
            if self._days >= MIN_DAYS_FOR_AVERAGE
            else None
        )
        self._totals.update(counts)
        self._days += 1
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

        lines = [
            f"{_plural(counts['combat'], 'fight')}, "
            f"{_plural(counts['gossip'], 'rumour')}, "
            f"{_plural(counts['trade'] + counts['gift'], 'trade')}",
            f"{facts.population} alive ({facts.population - previous_population:+d} overnight)",
            f"{_plural(facts.tribes, 'tribe')}, {self._war_state(counts, facts)}",
        ]
        toll = self._toll(deaths)
        if toll:
            lines.append(toll)
        season_line = self._season_line(facts, changed=previous_season != facts.season)
        if season_line:
            lines.append(season_line)

        return DayReport(
            day=facts.day,
            season=facts.season,
            headline=_headline(counts, facts, deaths, averages),
            lines=tuple(lines),
            counts=dict(counts),
        )

    @staticmethod
    def _toll(deaths: Counter[str]) -> str:
        """The day's deaths, by cause, or nothing on a day nobody died."""
        if not deaths:
            return ""
        parts = [
            f"{count} of {cause.replace('_', ' ')}"
            for cause, count in sorted(deaths.items(), key=lambda item: (-item[1], item[0]))
        ]
        return f"Died: {', '.join(parts)}"

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
