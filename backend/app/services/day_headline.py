"""Choosing what a day was *about*.

Pure functions over the day's tallies, kept apart from the chronicle that
collects them: this is the half with opinions in it.

The rule, learned from watching a live run print its cards rather than from
reasoning about it: on this island nearly everything happens every day -
about 32 coups, 3.5 wars, 126 fights, 537 rumours - so a headline ordered by
how dramatic an event *sounds* reads "chiefs overthrown" every single day.
What makes a day worth announcing is what it had unusually many of, measured
against that world's own running average.
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from app.services.day_facts import DayFacts

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


@dataclass(frozen=True, slots=True)
class Notable:
    """An event type worth leading with, and how to say it."""

    kind: str
    singular: str
    plural: str | None = None
    floor: int = 3
    """Below this many in a day, a ratio is noise rather than news."""


NOTABLE: tuple[Notable, ...] = (
    Notable("aged_out", "death of old age", "deaths of old age", floor=3),
    Notable("killed", "killing", floor=3),
    Notable("starved", "death by hunger", "deaths by hunger", floor=3),
    Notable("died_of_thirst", "death from thirst", "deaths from thirst", floor=3),
    Notable("plagued", "death from the plague", "deaths from the plague", floor=2),
    Notable("smitten", "death by lightning", "deaths by lightning", floor=1),
    Notable("war_declared", "war declared", "wars declared", floor=2),
    Notable("raid", "raid", floor=2),
    Notable("coup", "chief overthrown", "chiefs overthrown", floor=5),
    Notable("tribe_founded", "new tribe", "new tribes", floor=2),
    Notable("tribe_split", "tribe split apart", "tribes split apart", floor=1),
    Notable("tribe_left", "walked out of their tribe", "walked out of their tribes", floor=5),
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
"""How far above anything recent a count has to be to lead."""

MIN_DAYS_FOR_AVERAGE = 2
"""Days of history before ratios mean anything. Until then, fixed rules."""

AVERAGE_WINDOW_DAYS = 7
"""How many days "recent" means.

"Usual" was the *lifetime mean* for one night, and a fifty-day run showed
why that is wrong: alliances grow as the island does - 99 a day, then 110,
129, 172, 197, 315 - so against a lifetime mean they were five times the
usual every single day, and six of twelve consecutive cards led with them.

A trailing mean is better and still not right: anything growing at a fifth
a day is genuinely double its week-old self, for ever. So the baseline is
the *peak* of the window rather than its mean - today has to beat anything
the island has recently managed, which is what "unusual" means for a
series that trends. A real spike still clears it easily; steady growth
does not.
"""


def plural(count: int, singular: str, plural: str | None = None) -> str:
    """`1 war`, `3 wars` - with an irregular plural when one is given."""
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def _multiple(ratio: float) -> str:
    """How a person would say "2.9 times as many as any recent day"."""
    if ratio >= 4.0:
        return f"{ratio:.0f}x any recent day"
    if ratio >= 2.6:
        return "triple any recent day"
    if ratio >= 1.9:
        return "double any recent day"
    return "more than any recent day"


def _spike(counts: Counter[str], peaks: Mapping[str, float]) -> str | None:
    """The day's biggest outlier against anything recent, if it has one."""
    best: tuple[float, str] | None = None
    for notable in NOTABLE:
        count = counts[notable.kind]
        if count < notable.floor:
            continue
        peak = peaks.get(notable.kind, 0.0)
        ratio = count / peak if peak >= 1.0 else float("inf")
        if ratio < SPIKE:
            continue
        said = f"{plural(count, notable.singular, notable.plural)}"
        phrase = said if ratio == float("inf") else f"{said} - {_multiple(ratio)}"
        score = 99.0 if ratio == float("inf") else ratio
        if best is None or score > best[0]:
            best = (score, phrase[0].upper() + phrase[1:])
    return None if best is None else best[1]


def headline(
    counts: Counter[str],
    facts: DayFacts,
    deaths: Counter[str],
    peaks: Mapping[str, float] | None = None,
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
        return f"The island is nearly empty: {plural(facts.population, 'survivor')} left"
    if deaths["old_age"] >= COHORT_DEATHS and facts.founders_alive > 0:
        # The die-off lasts about ten days, and saying the same sentence ten
        # times is the monotony these rules exist to avoid. The first day is
        # the news; after that the running total is.
        so_far = facts.deaths_by_cause.get("old_age", deaths["old_age"])
        if so_far == deaths["old_age"]:
            return (
                f"The founding generation is going: {plural(deaths['old_age'], 'death')} of old age"
            )
        return f"{deaths['old_age']} more founders gone - {so_far} of old age so far"
    if peaks is not None:
        # With history, the question is only what was unusual. Falling
        # through to the fixed rules here is what made every card lead with
        # a coup: they fire on *any* count, and this island has coups daily.
        return _spike(counts, peaks) or _ordinary_day(counts)

    # No history yet - the first two days of a world. Fixed order, and the
    # only place it is still right, because nothing has a usual yet.
    if counts["killed"] >= COHORT_DEATHS:
        return f"{plural(counts['killed'], 'killing')} on the island"
    if counts["starved"] >= COHORT_DEATHS:
        return f"Hunger: {plural(counts['starved'], 'death')}"
    if total >= 3:
        return f"{plural(total, 'death')} on the island"
    if counts["war_declared"]:
        return f"War: {plural(counts['war_declared'], 'declaration')} between tribes"
    if counts["coup"]:
        return f"{plural(counts['coup'], 'chief')} overthrown"
    if counts["tribe_founded"]:
        return f"{plural(counts['tribe_founded'], 'new tribe')} founded"
    if counts["peace_made"]:
        return f"Peace: {plural(counts['peace_made'], 'truce')} agreed"
    if counts["birth"]:
        return f"{plural(counts['birth'], 'child')} born"
    if counts["shelter_built"] >= 3:
        return f"Building: {plural(counts['shelter_built'], 'hut')} went up"
    if total:
        return f"{plural(total, 'death')} on the island"
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
