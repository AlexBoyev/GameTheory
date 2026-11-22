"""Trust, reputation and gossip (SPEC section 6).

The distinction that makes the social layer work:

* **trust** is first-hand. It only moves when the two of them actually did
  something to each other.
* **reputation** is second-hand. It is what you have been *told*, weighted by
  how much you trust whoever told you.

Keeping them separate is what lets a liar be believed by strangers and
ignored by the people who know better.
"""

from app.ai.memory import AgentMemory, MemoryEvent, Relationship
from app.sim.entities import Agent, Traits
from app.sim.events import EventType

TRUST_MIN = -1.0
TRUST_MAX = 1.0

COOPERATION_TRUST = 0.12
DEFECTION_TRUST = -0.22
BETRAYAL_TRUST = -0.5
"""Defecting on someone who trusted you costs far more than ordinary defection."""

BETRAYAL_THRESHOLD = 0.3
"""Trust above which a defection is remembered as a betrayal, not a slight."""

GIFT_TRUST = 0.18
SHARED_HUNT_TRUST = 0.2
ATTACK_TRUST = -0.6

GOSSIP_WEIGHT = 0.35
"""How far a fully-trusted speaker can move your belief in one conversation."""

LIE_BASE_DETECTION = 0.2
CONTRADICTION_BONUS = 0.45
"""Catching a lie is far easier when you have first-hand evidence against it."""

CAUGHT_LIAR_TRUST = -0.4
CAUGHT_LIAR_REPUTATION = -0.35


def clamp_trust(value: float) -> float:
    """Clamp a trust or reputation value to `[-1, 1]`."""
    return max(TRUST_MIN, min(TRUST_MAX, value))


def adjust_trust(relationship: Relationship, delta: float) -> float:
    """Move trust by `delta`, clamped. Returns the new value."""
    relationship.trust = clamp_trust(relationship.trust + delta)
    return relationship.trust


def is_betrayal(relationship: Relationship) -> bool:
    """Whether defecting on this partner now counts as a betrayal."""
    return relationship.trust >= BETRAYAL_THRESHOLD


def record_round(
    memory: AgentMemory,
    partner_id: int,
    own_move: str,
    partner_move: str,
    payoff: float,
    tick: int,
) -> Relationship:
    """Write one game round into memory and return the relationship."""
    relationship = memory.relationship(partner_id)
    relationship.moves.append(partner_move)
    relationship.own_moves.append(own_move)
    relationship.payoffs.append(payoff)
    relationship.interactions += 1
    relationship.last_tick = tick
    return relationship


def effective_opinion(memory: AgentMemory, target_id: int) -> float:
    """First-hand trust if there is any, otherwise hearsay (SPEC 5.2)."""
    relationship = memory.social.get(target_id)
    if relationship is None:
        return 0.0
    if relationship.interactions > 0:
        return relationship.trust
    return relationship.reputation


def apply_gossip(
    listener: AgentMemory,
    speaker_id: int,
    target_id: int,
    claim: float,
) -> float:
    """Fold a claim about `target_id` into the listener's reputation belief.

    The update is weighted by the listener's trust in the speaker, so a
    stranger's slander barely registers and a friend's warning lands hard.
    Returns the new belief.
    """
    speaker = listener.relationship(speaker_id)
    about = listener.relationship(target_id)

    # Trust in [-1, 1] -> credence in [0, 1]. A distrusted speaker moves you
    # a little; a hated one does not move you at all.
    credence = max(0.0, (speaker.trust + 1.0) / 2.0)
    weight = credence * GOSSIP_WEIGHT
    about.reputation = clamp_trust(about.reputation + (claim - about.reputation) * weight)
    return about.reputation


def lie_detection_chance(
    speaker: Traits,
    listener: Traits,
    listener_knows_better: bool,
) -> float:
    """Chance the listener sees through a false claim.

    First-hand evidence dominates: it is hard to convince someone that their
    friend steals when that friend has been feeding them all week.
    """
    chance = LIE_BASE_DETECTION
    chance += 0.3 * listener.cunning
    chance -= 0.3 * speaker.cunning
    chance += 0.2 * (1.0 - speaker.honesty)
    if listener_knows_better:
        chance += CONTRADICTION_BONUS
    return max(0.02, min(0.95, chance))


def punish_caught_liar(listener: AgentMemory, speaker_id: int) -> None:
    """Record that `speaker_id` was caught lying to this agent."""
    relationship = listener.relationship(speaker_id)
    relationship.caught_lying += 1
    adjust_trust(relationship, CAUGHT_LIAR_TRUST)
    relationship.reputation = clamp_trust(relationship.reputation + CAUGHT_LIAR_REPUTATION)


def remember(
    memory: AgentMemory,
    *,
    tick: int,
    sim_seconds: float,
    event_type: EventType,
    summary: str,
    actors: tuple[int, ...],
    importance: int,
) -> None:
    """Append an episodic memory."""
    memory.remember(
        MemoryEvent(
            tick=tick,
            sim_seconds=sim_seconds,
            type=event_type,
            summary=summary,
            actors=actors,
            importance=importance,
        )
    )


def relative_advantage(agent: Agent, other: Agent) -> float:
    """How much stronger `agent` is than `other`, in `[-1, 1]`.

    Health and carried food, because those are what a confrontation is
    actually about.
    """
    mine = agent.health + agent.inventory.food * 8.0
    theirs = other.health + other.inventory.food * 8.0
    total = mine + theirs
    if total <= 0:
        return 0.0
    return max(-1.0, min(1.0, (mine - theirs) / total))
