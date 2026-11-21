"""Encounters: picking a game from context and applying its payoffs (SPEC 5.1)."""

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


class EncounterResolver:
    """Chooses a game for a pair, asks both strategies, applies the payoffs.

    Phase 4 implements selection, trembling-hand noise and the trust/food
    consequences; the result type is fixed here so metrics and the event feed
    can be built against it.
    """

    __slots__ = ("payoffs", "trembling_hand")

    def __init__(
        self,
        payoffs: dict[GameKind, PayoffMatrix] | None = None,
        trembling_hand: float = 0.02,
    ) -> None:
        self.payoffs = payoffs or {GameKind.PRISONERS_DILEMMA: PayoffMatrix()}
        self.trembling_hand = trembling_hand

    def resolve(self, agent_a: int, agent_b: int) -> EncounterResult:
        """Resolve an encounter between two agents."""
        msg = "EncounterResolver.resolve() arrives in Phase 4 (game theory)"
        raise NotImplementedError(msg)
