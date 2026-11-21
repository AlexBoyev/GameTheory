"""Episodic and social memory (SPEC section 7.2).

Retrieval is `importance x recency x relevance`, which is also the ranking used
to pick the top-K memories that go into an LLM prompt.
"""

from collections import deque
from dataclasses import dataclass, field

from app.sim.events import EventType

RECENCY_HALF_LIFE_SIM_S: float = 600.0
"""Sim-seconds after which a memory's recency weight halves."""


@dataclass(frozen=True, slots=True)
class MemoryEvent:
    """Something the agent experienced or was told about.

    Attributes:
        tick: When it was recorded.
        sim_seconds: Sim-time of recording, used for recency decay.
        type: Event kind.
        actors: Other agents involved.
        summary: Short line, also shown in the inspector and LLM prompts.
        importance: 1-10.
    """

    tick: int
    sim_seconds: float
    type: EventType
    summary: str
    actors: tuple[int, ...] = ()
    importance: int = 3


HISTORY_LENGTH = 16
"""How many rounds of a pairing are remembered. Enough for every strategy in
SPEC 5.2 to see what it needs, bounded so a long-lived pair cannot grow
without limit."""


@dataclass(slots=True)
class Relationship:
    """What one agent believes about another (SPEC section 6).

    Trust is first-hand and only moves when these two actually did something
    to each other; reputation is hearsay. Keeping them apart is what lets a
    liar be believed by strangers and ignored by friends.

    Attributes:
        trust: `[-1, 1]`; updated by outcomes, gifts, betrayals and gossip.
        reputation: Second-hand belief about the partner's character.
        moves: Last K moves the partner played against us ("C"/"D").
        own_moves: Last K moves we played against them.
        payoffs: What each of those rounds paid us - Pavlov needs it.
        interactions: Total encounters.
        last_tick: Tick of the most recent interaction.
        is_ally: Explicit pact in force.
        caught_lying: Times we caught them lying.
        betrayals: Times they defected on us while we trusted them.
    """

    trust: float = 0.0
    reputation: float = 0.0
    moves: deque[str] = field(default_factory=lambda: deque(maxlen=HISTORY_LENGTH))
    own_moves: deque[str] = field(default_factory=lambda: deque(maxlen=HISTORY_LENGTH))
    payoffs: deque[float] = field(default_factory=lambda: deque(maxlen=HISTORY_LENGTH))
    interactions: int = 0
    last_tick: int = 0
    is_ally: bool = False
    caught_lying: int = 0
    betrayals: int = 0


@dataclass(slots=True)
class AgentMemory:
    """Per-agent working, episodic and social memory."""

    episodic: deque[MemoryEvent] = field(default_factory=lambda: deque(maxlen=64))
    social: dict[int, Relationship] = field(default_factory=dict)
    beliefs: list[str] = field(default_factory=list)
    last_observation_tick: int = -1

    def remember(self, event: MemoryEvent) -> None:
        """Store `event`, evicting the oldest when the buffer is full."""
        self.episodic.append(event)

    def relationship(self, other_id: int) -> Relationship:
        """Return (creating if needed) the relationship with `other_id`."""
        relationship = self.social.get(other_id)
        if relationship is None:
            relationship = Relationship()
            self.social[other_id] = relationship
        return relationship

    def recall(
        self, now_sim_s: float, limit: int = 5, about: int | None = None
    ) -> list[MemoryEvent]:
        """Return the `limit` most relevant memories, best first.

        Score is `importance * 0.5 ** (age / half_life)`, doubled when `about`
        appears among the memory's actors.
        """

        def score(event: MemoryEvent) -> float:
            age = max(0.0, now_sim_s - event.sim_seconds)
            recency = float(0.5 ** (age / RECENCY_HALF_LIFE_SIM_S))
            relevance = 2.0 if about is not None and about in event.actors else 1.0
            return event.importance * recency * relevance

        return sorted(self.episodic, key=score, reverse=True)[:limit]

    def top_relationships(self, limit: int = 5) -> list[tuple[int, Relationship]]:
        """Return the strongest relationships by absolute trust."""
        ranked = sorted(self.social.items(), key=lambda item: -abs(item[1].trust))
        return ranked[:limit]
