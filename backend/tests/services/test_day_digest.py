"""The day card: what it leads with, and what it refuses to invent."""

from app.services.day_digest import DayChronicle, DayFacts


def facts(day: int, **overrides: object) -> DayFacts:
    """A day's worth of state, with sensible defaults."""
    base: dict[str, object] = {
        "day": day,
        "season": "spring",
        "population": 100,
        "tribes": 0,
        "tribes_at_war": 0,
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
    chronicle.record(events(death=4))

    report = chronicle.turn(facts(1, population=96))

    assert report is not None
    assert "4 deaths" in report.headline
    assert "96 alive (-4 overnight)" in report.lines[1]


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
