"""Encounters: picking a game from context and living with the result (SPEC 5.1).

The resolver is the heart of the whole project. Two agents meet; the context
decides *which* game they are in; their inherited strategies decide the moves;
the payoff matrix decides the score; and then - the part that matters - the
result is converted into food, health, trust and memory, so the next encounter
between these two is shaped by this one.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.ai.gametheory.strategies import Move


class GameKind(StrEnum):
    """Which game an encounter resolves as."""

    PRISONERS_DILEMMA = "prisoners_dilemma"
    STAG_HUNT = "stag_hunt"
    HAWK_DOVE = "hawk_dove"
    ULTIMATUM = "ultimatum"
    PUBLIC_GOODS = "public_goods"


@dataclass(frozen=True, slots=True)
class PayoffMatrix:
    """Symmetric 2x2 payoffs in the classic T/R/P/S notation.

    Attributes:
        temptation: Defect while the partner cooperates.
        reward: Both cooperate.
        punishment: Both defect.
        sucker: Cooperate while the partner defects.
    """

    temptation: float = 5.0
    reward: float = 3.0
    punishment: float = 1.0
    sucker: float = 0.0

    def payoff(self, own: Move, other: Move) -> float:
        """Return our payoff for the move pair."""
        if own is Move.COOPERATE:
            return self.reward if other is Move.COOPERATE else self.sucker
        return self.temptation if other is Move.COOPERATE else self.punishment

    @property
    def is_dilemma(self) -> bool:
        """True when `T > R > P > S`, i.e. a genuine Prisoner's Dilemma."""
        return self.temptation > self.reward > self.punishment > self.sucker


@dataclass(frozen=True, slots=True)
class EncounterResult:
    """Outcome of one resolved encounter, logged to memory and metrics."""

    game: GameKind
    agent_a: int
    agent_b: int
    move_a: Move
    move_b: Move
    payoff_a: float
    payoff_b: float
    trembled: bool = False
    betrayal_by: tuple[int, ...] = ()
    food_moved: float = 0.0
    summary: str = ""

    @property
    def mutual_cooperation(self) -> bool:
        """Both played C - the outcome the whole society depends on."""
        return self.move_a is Move.COOPERATE and self.move_b is Move.COOPERATE

    @property
    def cooperations(self) -> int:
        """How many of the two moves were cooperative."""
        return sum(move is Move.COOPERATE for move in (self.move_a, self.move_b))
