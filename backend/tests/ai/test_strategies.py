"""Every strategy's move table (SPEC section 5.2).

These are the rules of the experiment. If Tit-for-Tat stops retaliating or
Grudger starts forgiving, every result the simulation has ever produced is
meaningless - so each one is pinned here explicitly.
"""

import pytest

from app.ai.gametheory.strategies import (
    AlwaysCooperate,
    AlwaysDefect,
    Detective,
    GenerousTitForTat,
    Grudger,
    LLMStrategy,
    Move,
    Opportunist,
    Pavlov,
    RandomStrategy,
    StrategyContext,
    TitForTat,
    build_strategy_registry,
)

C = Move.COOPERATE
D = Move.DEFECT


def ctx(partner: str = "", own: str = "", **kwargs: float) -> StrategyContext:
    """Build a context from compact move strings like "CCD"."""
    return StrategyContext(
        partner_moves=tuple(Move(ch) for ch in partner),
        own_moves=tuple(Move(ch) for ch in own),
        **kwargs,  # type: ignore[arg-type]
    )


def test_the_registry_holds_every_strategy_in_the_spec() -> None:
    registry = build_strategy_registry()

    assert set(registry.names) == {
        "AlwaysCooperate",
        "AlwaysDefect",
        "TitForTat",
        "GenerousTFT",
        "Grudger",
        "Pavlov",
        "Detective",
        "Random",
        "Opportunist",
        "LLM",
    }


def test_always_cooperate_and_always_defect_never_waver() -> None:
    for history in ("", "C", "D", "DDDD", "CCCC"):
        assert AlwaysCooperate().move(ctx(history)) is C
        assert AlwaysDefect().move(ctx(history)) is D


def test_tit_for_tat_opens_with_trust_then_mirrors() -> None:
    strategy = TitForTat()

    assert strategy.move(ctx("")) is C, "must open cooperatively"
    assert strategy.move(ctx("C")) is C
    assert strategy.move(ctx("D")) is D
    assert strategy.move(ctx("DC")) is C, "mirrors the *last* move, not the worst"


def test_tit_for_tat_punishes_always_defect_from_round_two() -> None:
    """The canonical pairing: one free lunch, then nothing (SPEC 5.2)."""
    tft, defector = TitForTat(), AlwaysDefect()
    tft_moves: list[Move] = []
    defector_moves: list[Move] = []

    for _ in range(10):
        tft_move = tft.move(ctx("".join(m.value for m in defector_moves)))
        defector_move = defector.move(ctx("".join(m.value for m in tft_moves)))
        tft_moves.append(tft_move)
        defector_moves.append(defector_move)

    assert tft_moves[0] is C, "exploited exactly once"
    assert all(move is D for move in tft_moves[1:]), "and never again"
    assert all(move is D for move in defector_moves)


def test_grudger_never_forgives() -> None:
    strategy = Grudger()

    assert strategy.move(ctx("CCCC")) is C
    assert strategy.move(ctx("CCDC")) is D
    # Twenty rounds of perfect cooperation after one defection: still no.
    assert strategy.move(ctx("D" + "C" * 20)) is D


def test_generous_tit_for_tat_forgives_sometimes() -> None:
    strategy = GenerousTitForTat()

    assert strategy.move(ctx("C", roll=0.99)) is C
    assert strategy.move(ctx("D", roll=0.99)) is D, "usually retaliates"
    assert strategy.move(ctx("D", roll=0.01)) is C, "but sometimes forgives"


def test_pavlov_stays_when_winning_and_shifts_when_losing() -> None:
    strategy = Pavlov()
    reward = 3.0

    assert strategy.move(ctx()) is C, "opens cooperatively"
    # Won with C: keep cooperating.
    assert strategy.move(ctx("C", "C", reward=reward, own_payoffs=(reward,))) is C
    # Lost with C (got suckered): switch to D.
    assert strategy.move(ctx("D", "C", reward=reward, own_payoffs=(0.0,))) is D
    # Won with D: keep defecting.
    assert strategy.move(ctx("C", "D", reward=reward, own_payoffs=(5.0,))) is D
    # Lost with D: switch back.
    assert strategy.move(ctx("D", "D", reward=reward, own_payoffs=(1.0,))) is C


def test_detective_probes_then_exploits_the_meek() -> None:
    strategy = Detective()

    # The probe is fixed: C, D, C, C.
    assert strategy.move(ctx("")) is C
    assert strategy.move(ctx("C")) is D
    assert strategy.move(ctx("CC")) is C
    assert strategy.move(ctx("CCC")) is C

    # Never punished -> exploit forever.
    assert strategy.move(ctx("CCCC")) is D
    assert strategy.move(ctx("CCCCC")) is D


def test_detective_mirrors_anyone_who_fights_back() -> None:
    strategy = Detective()

    assert strategy.move(ctx("CCDC")) is C, "they retaliated, so fall back to TFT"
    assert strategy.move(ctx("CCDD")) is D


def test_random_splits_on_the_roll() -> None:
    assert RandomStrategy().move(ctx(roll=0.1)) is C
    assert RandomStrategy().move(ctx(roll=0.9)) is D


def test_opportunist_defects_only_when_it_pays() -> None:
    strategy = Opportunist()

    greedy = ctx(greed=1.0, honesty=0.0, advantage=1.0, trust=0.0)
    assert strategy.move(greedy) is D

    honest = ctx(greed=1.0, honesty=1.0, advantage=1.0, trust=0.0)
    assert strategy.move(honest) is C, "honesty blocks the temptation"

    trusted = ctx(greed=1.0, honesty=0.0, advantage=0.0, trust=1.0)
    assert strategy.move(trusted) is C, "a friend gets the benefit of the doubt"


def test_llm_strategy_plays_competently_until_phase_5() -> None:
    strategy = LLMStrategy()

    assert strategy.move(ctx("")) is C
    assert strategy.move(ctx("D")) is D, "must not be free food"


@pytest.mark.parametrize("name", build_strategy_registry().names)
def test_every_strategy_returns_a_legal_move(name: str) -> None:
    strategy = build_strategy_registry().require(name)  # type: ignore[arg-type]

    for history in ("", "C", "D", "CDCD", "DDDD"):
        assert strategy.move(ctx(history, history)) in {C, D}
