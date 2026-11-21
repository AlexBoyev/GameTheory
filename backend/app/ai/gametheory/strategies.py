"""Strategies: the inherited "gene" that decides cooperate vs defect (SPEC 5.2)."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from app.core.world_config import StrategyName


class Move(StrEnum):
    """A move in a two-player game."""

    COOPERATE = "C"
    DEFECT = "D"


@dataclass(slots=True)
class StrategyContext:
    """What a strategy is allowed to see before moving.

    Attributes:
        own_moves: Our past moves against this partner, oldest first.
        partner_moves: Their past moves against us, oldest first.
        trust: Our trust in them, `[-1, 1]`.
        reputation: Gossip-derived belief when we have never met them.
        own_payoffs: Our payoff from each past round.
        greed: Trait shortcut for trait-driven strategies.
        honesty: Trait shortcut for trait-driven strategies.
        advantage: Our relative strength/resources versus theirs, `[-1, 1]`.
    """

    own_moves: tuple[Move, ...] = ()
    partner_moves: tuple[Move, ...] = ()
    trust: float = 0.0
    reputation: float = 0.0
    own_payoffs: tuple[float, ...] = ()
    greed: float = 0.5
    honesty: float = 0.5
    advantage: float = 0.0
    extra: dict[str, float] = field(default_factory=dict)

    @property
    def round_index(self) -> int:
        """How many rounds we have already played against this partner."""
        return len(self.partner_moves)

    @property
    def was_betrayed(self) -> bool:
        """True if the partner has ever defected on us."""
        return Move.DEFECT in self.partner_moves


class Strategy(Protocol):
    """Decides a move from the pair's history. Pure and deterministic.

    Any randomness must be drawn from the injected RNG stream by the caller and
    passed in via `StrategyContext.extra`, never from the global RNG.
    """

    name: StrategyName

    def move(self, ctx: StrategyContext) -> Move:
        """Return the move to play this round."""
        ...


class StrategyRegistry:
    """Name -> strategy lookup, populated in Phase 4."""

    __slots__ = ("_strategies",)

    def __init__(self) -> None:
        self._strategies: dict[StrategyName, Strategy] = {}

    def __len__(self) -> int:
        return len(self._strategies)

    def register(self, strategy: Strategy) -> None:
        """Register `strategy` under its name."""
        if strategy.name in self._strategies:
            msg = f"duplicate strategy: {strategy.name}"
            raise ValueError(msg)
        self._strategies[strategy.name] = strategy

    def get(self, name: StrategyName) -> Strategy | None:
        """Return the strategy called `name`, or `None`."""
        return self._strategies.get(name)

    @property
    def names(self) -> tuple[StrategyName, ...]:
        """Registered strategy names, sorted."""
        return tuple(sorted(self._strategies))
