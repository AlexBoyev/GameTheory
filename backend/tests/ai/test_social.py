"""Trust, reputation, gossip and lie detection (SPEC section 6).

The arithmetic here decides whether a liar can get away with it, so it is
pinned rather than assumed.
"""

import pytest

from app.ai import social
from app.ai.memory import AgentMemory
from app.sim.entities import Traits


def test_trust_is_clamped_to_the_unit_range() -> None:
    relationship = AgentMemory().relationship(1)

    social.adjust_trust(relationship, 5.0)
    assert relationship.trust == 1.0

    social.adjust_trust(relationship, -50.0)
    assert relationship.trust == -1.0


def test_first_hand_trust_beats_hearsay() -> None:
    memory = AgentMemory()
    relationship = memory.relationship(7)
    relationship.reputation = -0.9

    assert social.effective_opinion(memory, 7) == pytest.approx(-0.9), "hearsay until we meet"

    relationship.interactions = 1
    relationship.trust = 0.5
    assert social.effective_opinion(memory, 7) == pytest.approx(0.5), "experience overrides rumour"


def test_gossip_moves_belief_towards_the_claim() -> None:
    memory = AgentMemory()
    memory.relationship(1).trust = 1.0  # we fully trust the speaker

    after = social.apply_gossip(memory, speaker_id=1, target_id=2, claim=-1.0)

    assert after < 0.0, "a trusted friend's warning lands"
    assert after > -1.0, "but one conversation is not the whole truth"


def test_a_distrusted_speaker_barely_moves_anything() -> None:
    trusted = AgentMemory()
    trusted.relationship(1).trust = 1.0
    hated = AgentMemory()
    hated.relationship(1).trust = -1.0

    from_friend = social.apply_gossip(trusted, 1, 2, claim=-1.0)
    from_enemy = social.apply_gossip(hated, 1, 2, claim=-1.0)

    assert abs(from_friend) > abs(from_enemy)
    assert from_enemy == pytest.approx(0.0), "someone you hate cannot tell you anything"


def test_gossip_converges_rather_than_overshooting() -> None:
    memory = AgentMemory()
    memory.relationship(1).trust = 1.0

    belief = 0.0
    for _ in range(50):
        belief = social.apply_gossip(memory, 1, 2, claim=-1.0)

    assert -1.0 <= belief <= -0.9, "repetition approaches the claim without passing it"


def test_evidence_makes_a_lie_much_easier_to_catch() -> None:
    liar = Traits(cunning=0.5, honesty=0.2)
    listener = Traits(cunning=0.5)

    blind = social.lie_detection_chance(liar, listener, listener_knows_better=False)
    informed = social.lie_detection_chance(liar, listener, listener_knows_better=True)

    assert informed > blind
    assert 0.0 < blind < informed <= 0.95


def test_a_cunning_liar_is_harder_to_catch() -> None:
    listener = Traits(cunning=0.5)
    slick = social.lie_detection_chance(Traits(cunning=1.0, honesty=0.0), listener, False)
    clumsy = social.lie_detection_chance(Traits(cunning=0.0, honesty=0.0), listener, False)

    assert slick < clumsy


def test_being_caught_costs_trust_and_reputation() -> None:
    memory = AgentMemory()
    relationship = memory.relationship(3)
    relationship.trust = 0.5

    social.punish_caught_liar(memory, 3)

    assert relationship.caught_lying == 1
    assert relationship.trust < 0.5
    assert relationship.reputation < 0.0


def test_betrayal_only_counts_when_there_was_trust_to_betray() -> None:
    memory = AgentMemory()
    stranger = memory.relationship(1)
    friend = memory.relationship(2)
    friend.trust = 0.8

    assert not social.is_betrayal(stranger)
    assert social.is_betrayal(friend)


def test_recording_a_round_keeps_both_sides_of_the_history() -> None:
    memory = AgentMemory()

    social.record_round(memory, 5, own_move="C", partner_move="D", payoff=0.0, tick=10)

    relationship = memory.social[5]
    assert list(relationship.own_moves) == ["C"]
    assert list(relationship.moves) == ["D"]
    assert list(relationship.payoffs) == [0.0]
    assert relationship.interactions == 1
    assert relationship.last_tick == 10
