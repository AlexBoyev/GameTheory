"""The day card: what it leads with, and what it refuses to invent."""

from app.services.day_digest import DayChronicle
from app.services.day_facts import DayFacts


def facts(day: int, **overrides: object) -> DayFacts:
    """A day's worth of state, with sensible defaults.

    `deaths_by_cause` is cumulative, as the world reports it: the chronicle
    takes the difference between turns, so a test that wants three deaths
    "today" passes a total three higher than the day before.
    """
    base: dict[str, object] = {
        "day": day,
        "season": "spring",
        "population": 100,
        "tribes": 0,
        "tribes_at_war": 0,
        # The founding cast is still around unless a test says otherwise:
        # old age only leads a day while they are the ones dying.
        "founders_alive": 100,
        "deaths_by_cause": {},
    }
    base.update(overrides)
    return DayFacts(**base)  # type: ignore[arg-type]


def events(**counts: int) -> list[dict[str, object]]:
    """`combat=2` becomes two combat events."""
    return [{"type": kind} for kind, count in counts.items() for _ in range(count)]


def test_the_first_turn_introduces_the_world_rather_than_summarising_it() -> None:
    chronicle = DayChronicle()

    report = chronicle.turn(facts(0, population=120))

    assert report is not None
    assert "120 strangers" in report.headline
    assert any("game" in line for line in report.lines), "it should say what you are watching"


def test_a_day_is_reported_once() -> None:
    chronicle = DayChronicle()
    chronicle.turn(facts(0))

    assert chronicle.seen(0)
    assert chronicle.turn(facts(0)) is None, "the same day must not announce itself twice"
    assert chronicle.turn(facts(1)) is not None


def test_a_war_outranks_a_loud_day_of_gossip() -> None:
    """Ordered rules, not a score: volume must not out-shout a war."""
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    chronicle.record(events(gossip=800, combat=200, war_declared=1))

    report = chronicle.turn(facts(1, tribes=4, tribes_at_war=2))

    assert report is not None
    assert report.headline.startswith("War:")
    assert "2 at war" in " ".join(report.lines)
    assert report.counts["gossip"] == 800


def test_the_card_never_contradicts_its_own_headline() -> None:
    """A war declared and settled inside one day is not "none at war"."""
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    chronicle.record(events(war_declared=1, peace_made=1))

    report = chronicle.turn(facts(1, tribes=13, tribes_at_war=0))

    assert report is not None
    assert report.headline.startswith("War:")
    joined = " ".join(report.lines)
    assert "none at war" not in joined
    assert "1 truce ended the fighting" in joined


def test_a_war_that_simply_stopped_says_so() -> None:
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    chronicle.record(events(war_declared=2))

    report = chronicle.turn(facts(1, tribes=5, tribes_at_war=0))

    assert report is not None
    assert "the war is already over" in " ".join(report.lines)


def test_a_headline_reports_the_unusual_not_the_dramatic() -> None:
    """The lesson of a live run: coups run at about 32 a day on this island.

    Ordered-by-drama put coups second, so every card led with one and every
    day looked like a crisis. A day is worth announcing for what it had
    unusually many of, measured against its own history.
    """
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    for day in (1, 2, 3):
        chronicle.record(events(coup=30, gossip=500))
        chronicle.turn(facts(day))

    chronicle.record(events(coup=31, gossip=505))
    ordinary = chronicle.turn(facts(4))
    assert ordinary is not None
    assert "overthrown" not in ordinary.headline, "32 coups is a Tuesday here"

    chronicle.record(events(coup=96, gossip=500))
    spike = chronicle.turn(facts(5))
    assert spike is not None
    assert "96 chiefs overthrown" in spike.headline
    assert "triple any recent day" in spike.headline


def test_the_first_thing_a_world_has_ever_done_is_news() -> None:
    """No history to compare against means it has never happened before."""
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    for day in (1, 2):
        chronicle.record(events(gossip=500))
        chronicle.turn(facts(day))

    chronicle.record(events(gossip=500, war_declared=2))
    report = chronicle.turn(facts(3, tribes=6, tribes_at_war=2))

    assert report is not None
    assert "2 wars declared" in report.headline
    assert "recent" not in report.headline, "nothing to compare it against"


def test_a_spike_below_its_floor_is_noise() -> None:
    """One raid where the average is a third of one is not a raiding season."""
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    for day in (1, 2, 3):
        chronicle.record(events(gossip=500))
        chronicle.turn(facts(day))

    chronicle.record(events(gossip=500, raid=1))
    report = chronicle.turn(facts(4))

    assert report is not None
    assert "raid" not in report.headline


def test_a_quiet_day_still_says_what_happened() -> None:
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    chronicle.record(events(gossip=40, trade=3, combat=12))

    report = chronicle.turn(facts(1))

    assert report is not None
    assert "trading" in report.headline
    assert "12 fights, 40 rumours, 3 trades" in report.lines[0]


def test_the_population_line_reads_as_a_change() -> None:
    chronicle = DayChronicle()
    chronicle.turn(facts(0, population=100))

    report = chronicle.turn(facts(1, population=96, deaths_by_cause={"combat": 2, "starvation": 2}))

    assert report is not None
    assert "4 deaths" in report.headline
    assert "96 alive (-4 overnight)" in report.lines[1]
    assert "Died: 2 of combat, 2 of starvation" in report.lines


def test_deaths_are_counted_from_the_world_not_the_feed() -> None:
    """The feed is a bounded queue that drops batches when a client is slow.

    It drops them hardest when the island is busiest, which is exactly when
    the number matters, so the chronicle takes the difference between the
    world's own cumulative tallies instead.
    """
    chronicle = DayChronicle()
    chronicle.turn(facts(0, deaths_by_cause={"old_age": 5}))
    chronicle.record(events(death=99))  # nonsense from the feed, ignored

    report = chronicle.turn(facts(1, population=97, deaths_by_cause={"old_age": 8}))

    assert report is not None
    # Three today, not ninety-nine; and the world knew five had already gone.
    assert report.headline == "3 more founders gone - 8 of old age so far"
    assert "Died: 3 of old age" in report.lines


def test_the_founding_generation_dying_is_its_own_story() -> None:
    """The island starts with nobody old, so they age and die together.

    Measured on the default world: first old-age death on day 8, then ten
    days of decline before the children refill it. That turn used to be
    reported as "9 deaths on the island".
    """
    chronicle = DayChronicle()
    chronicle.turn(facts(7, population=140, deaths_by_cause={"combat": 4}))

    report = chronicle.turn(
        facts(8, population=131, tribes=12, deaths_by_cause={"combat": 4, "old_age": 9})
    )

    assert report is not None
    assert "founding generation" in report.headline
    assert "9 deaths of old age" in report.headline

    # It lasts about ten days, and ten identical cards is the monotony the
    # headline rules exist to avoid.
    second = chronicle.turn(facts(9, population=124, deaths_by_cause={"combat": 4, "old_age": 16}))
    assert second is not None
    assert second.headline == "7 more founders gone - 16 of old age so far"


def test_a_collapse_outranks_whatever_else_happened() -> None:
    """Reporting 3 deaths is true and useless when four people are left."""
    chronicle = DayChronicle()
    chronicle.turn(facts(4, population=60))
    chronicle.record(events(war_declared=2))

    report = chronicle.turn(facts(5, population=4, deaths_by_cause={"starvation": 56}))

    assert report is not None
    assert "nearly empty" in report.headline
    assert "4 survivors" in report.headline


def test_an_empty_island_says_so_plainly() -> None:
    chronicle = DayChronicle()
    chronicle.turn(facts(4, population=2))

    report = chronicle.turn(facts(5, population=0, deaths_by_cause={"starvation": 2}))

    assert report is not None
    assert report.headline == "The island is empty"


def test_winter_is_announced_because_the_calendar_guarantees_it() -> None:
    """The one honest thing to say about a day that has not happened yet."""
    chronicle = DayChronicle()
    chronicle.turn(facts(20, season="autumn"))

    report = chronicle.turn(facts(21, season="winter"))

    assert report is not None
    joined = " ".join(report.lines)
    assert "Winter begins" in joined
    assert "stop regrowing" in joined


def test_a_new_world_forgets_the_old_one() -> None:
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    chronicle.record(events(coup=3))

    chronicle.reset()

    assert not chronicle.seen(0)
    report = chronicle.turn(facts(0))
    assert report is not None
    assert "strangers" in report.headline, "a reset world opens, it does not continue"
    assert report.counts == {}


def test_a_bloody_day_leads_even_once_the_world_has_a_history() -> None:
    """Deaths were absolute rules once, and that was wrong both ways.

    Left absolute they headline every day, because deaths run at about
    three a day. Left out of the relative rule they could not headline at
    all, so a day with nine killings was announced by its alliances.
    """
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    for day in (1, 2, 3):
        chronicle.record(events(gossip=500, alliance=20))
        chronicle.turn(facts(day, deaths_by_cause={"combat": 2 * day}))

    chronicle.record(events(gossip=500, alliance=20))
    report = chronicle.turn(facts(4, population=91, deaths_by_cause={"combat": 15}))

    assert report is not None
    assert "9 killings" in report.headline
    assert "any recent day" in report.headline


def test_a_restored_world_is_not_a_new_one() -> None:
    """Loading a snapshot resets the chronicle; the island is still on day 13.

    The opening card would otherwise announce strangers washing ashore on
    a world with tribes, wars and a graveyard - a lie told by the one
    feature whose job is saying what is going on.
    """
    chronicle = DayChronicle()

    report = chronicle.turn(facts(12, population=117, tribes=9, tribes_at_war=2))

    assert report is not None
    assert "strangers" not in report.headline
    assert report.headline == "Day 13, picked up where it left off"
    assert "117 alive, 9 tribes, 2 at war" in report.lines[0]

    # And the next day is reported normally, against this as the baseline.
    chronicle.record(events(gossip=400))
    next_day = chronicle.turn(facts(13, population=115, tribes=9, tribes_at_war=2))
    assert next_day is not None
    assert "picked up" not in next_day.headline
    assert "115 alive (-2 overnight)" in next_day.lines[1]


def test_a_plague_leads_its_day() -> None:
    """A god tool that kills fourteen people is the story of that day.

    Only combat and starvation were counted, so a plague could be
    headlined by the day's alliances - the same gap that let a bloody day
    hide behind its gossip, left open for every cause the observer causes
    themselves.
    """
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    for day in (1, 2, 3):
        chronicle.record(events(gossip=500, alliance=20))
        chronicle.turn(facts(day))

    chronicle.record(events(gossip=500, alliance=20))
    report = chronicle.turn(facts(4, population=106, deaths_by_cause={"plague": 14}))

    assert report is not None
    assert "14 deaths from the plague" in report.headline
    assert "Died: 14 of plague" in report.lines


def test_every_headline_phrase_survives_being_pluralised() -> None:
    """A guard, because "3 struck down from the skys" shipped once.

    Anything with a space in it is a phrase rather than a noun, and the
    naive "add an s" cannot be trusted with those - so a phrase has to say
    what its plural is.
    """
    from app.services.day_headline import NOTABLE

    unsafe = [
        notable.singular
        for notable in NOTABLE
        if " " in notable.singular and notable.plural is None
    ]

    assert not unsafe, f"these need an explicit plural: {unsafe}"


def test_old_age_stops_being_the_story_once_the_founders_are_gone() -> None:
    """A fifty-day run was still announcing "4 more founders gone" on day 47.

    The founding generation is dead by about day 18. Everybody ageing out
    after that was born on the island, so old age becomes an ordinary
    cause competing with everything else rather than the story of the day.
    """
    chronicle = DayChronicle()
    chronicle.turn(facts(40, population=200, deaths_by_cause={"old_age": 140}))
    # A few ordinary days, one old-age death each: that is the "usual" the
    # next day is measured against.
    for index, day in enumerate((41, 42, 43), start=1):
        chronicle.record(events(gossip=500, alliance=30))
        chronicle.turn(
            facts(
                day,
                population=200,
                founders_alive=0,
                deaths_by_cause={"old_age": 140 + index},
            )
        )

    chronicle.record(events(gossip=500, alliance=30))
    report = chronicle.turn(
        facts(44, population=196, founders_alive=0, deaths_by_cause={"old_age": 147})
    )

    assert report is not None
    assert "founders" not in report.headline
    assert "4 deaths of old age" in report.headline


def test_a_growing_island_does_not_spike_against_its_own_past_forever() -> None:
    """Alliances led six of twelve consecutive days in a fifty-day run.

    They grow as the island does - 99 a day, then 110, 129, 172 - so
    against a lifetime average they are "5x the usual" permanently. The
    average has to be recent for growth to stop reading as news.
    """
    chronicle = DayChronicle()
    chronicle.turn(facts(0))
    alliances = 20
    headlines = []
    for day in range(1, 16):
        alliances = int(alliances * 1.2)  # a steadily growing island
        chronicle.record(events(gossip=400, alliance=alliances))
        report = chronicle.turn(facts(day, population=150))
        assert report is not None
        headlines.append(report.headline)

    led_by_alliances = [line for line in headlines[-8:] if "alliance" in line]
    assert not led_by_alliances, f"steady growth kept leading: {led_by_alliances}"
