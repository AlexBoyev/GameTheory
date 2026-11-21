"""Strategies: the inherited "gene" that decides cooperate vs defect (SPEC 5.2).

Every strategy is a pure function of the pair's history plus a few traits.
Randomness is never drawn here - the resolver rolls the dice from the seeded
`encounter` stream and passes the result in `StrategyContext.roll`, which is
what keeps a whole world reproducible from its seed.
"""

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
        own_payoffs: Our payoff from each past round, oldest first.
        trust: Our trust in them, `[-1, 1]`.
        reputation: Gossip-derived belief, used when we have never met.
        greed: Trait shortcut for trait-driven strategies.
        honesty: Trait shortcut for trait-driven strategies.
        advantage: Our relative strength versus theirs, `[-1, 1]`.
        roll: A uniform `[0, 1)` draw from the seeded encounter stream.
        reward: The matrix's mutual-cooperation payoff, for Pavlov.
    """

    own_moves: tuple[Move, ...] = ()
    partner_moves: tuple[Move, ...] = ()
    own_payoffs: tuple[float, ...] = ()
    trust: float = 0.0
    reputation: float = 0.0
    greed: float = 0.5
    honesty: float = 0.5
    advantage: float = 0.0
    roll: float = 0.5
    reward: float = 3.0
    extra: dict[str, float] = field(default_factory=dict)

    @property
    def round_index(self) -> int:
        """How many rounds we have already played against this partner."""
        return len(self.partner_moves)

    @property
    def first_meeting(self) -> bool:
        """True when we have no history with this partner."""
        return not self.partner_moves

    @property
    def was_betrayed(self) -> bool:
        """True if the partner has ever defected on us."""
        return Move.DEFECT in self.partner_moves

    @property
    def last_partner_move(self) -> Move | None:
        """Their most recent move, if any."""
        return self.partner_moves[-1] if self.partner_moves else None

    @property
    def last_own_move(self) -> Move | None:
        """Our most recent move, if any."""
        return self.own_moves[-1] if self.own_moves else None


class Strategy(Protocol):
    """Decides a move from the pair's history. Pure and deterministic."""

    name: StrategyName

    def move(self, ctx: StrategyContext) -> Move:
        """Return the move to play this round."""
        ...


# --------------------------------------------------------------- the classics


class AlwaysCooperate:
    """Never defects. Thrives among friends, food for everyone else."""

    name: StrategyName = "AlwaysCooperate"

    def move(self, ctx: StrategyContext) -> Move:
        """Cooperate, always."""
        return Move.COOPERATE


class AlwaysDefect:
    """Never cooperates."""

    name: StrategyName = "AlwaysDefect"

    def move(self, ctx: StrategyContext) -> Move:
        """Defect, always."""
        return Move.DEFECT


class TitForTat:
    """Cooperate first, then do whatever they did last. Axelrod's winner."""

    name: StrategyName = "TitForTat"

    def move(self, ctx: StrategyContext) -> Move:
        """Open with trust, then mirror."""
        return ctx.last_partner_move or Move.COOPERATE


class GenerousTitForTat:
    """Tit-for-Tat that forgives a defection now and then.

    Forgiveness is what breaks the mutual-recrimination spiral two TFT agents
    fall into when the trembling hand flips one move.
    """

    name: StrategyName = "GenerousTFT"
    forgiveness = 0.1

    def move(self, ctx: StrategyContext) -> Move:
        """Mirror, but forgive a defection with probability `forgiveness`."""
        last = ctx.last_partner_move
        if last is None or last is Move.COOPERATE:
            return Move.COOPERATE
        return Move.COOPERATE if ctx.roll < self.forgiveness else Move.DEFECT


class Grudger:
    """Cooperates until betrayed once, then never again."""

    name: StrategyName = "Grudger"

    def move(self, ctx: StrategyContext) -> Move:
        """Cooperate until the first defection, then defect forever."""
        return Move.DEFECT if ctx.was_betrayed else Move.COOPERATE


class Pavlov:
    """Win-stay, lose-shift.

    "Winning" means the last round paid at least as well as mutual
    cooperation; anything less is a reason to change tack.
    """

    name: StrategyName = "Pavlov"

    def move(self, ctx: StrategyContext) -> Move:
        """Repeat the last move if it paid, otherwise switch."""
        if not ctx.own_payoffs or ctx.last_own_move is None:
            return Move.COOPERATE
        won = ctx.own_payoffs[-1] >= ctx.reward
        if won:
            return ctx.last_own_move
        return Move.DEFECT if ctx.last_own_move is Move.COOPERATE else Move.COOPERATE


class Detective:
    """Probes with C, D, C, C, then exploits the meek and mirrors the rest."""

    name: StrategyName = "Detective"
    probe: tuple[Move, ...] = (Move.COOPERATE, Move.DEFECT, Move.COOPERATE, Move.COOPERATE)

    def move(self, ctx: StrategyContext) -> Move:
        """Run the probe, then decide what kind of partner this is."""
        index = ctx.round_index
        if index < len(self.probe):
            return self.probe[index]
        # Did they ever punish the probe's defection? If not, take them.
        if Move.DEFECT not in ctx.partner_moves:
            return Move.DEFECT
        return ctx.last_partner_move or Move.COOPERATE


class RandomStrategy:
    """A coin flip. The control group."""

    name: StrategyName = "Random"

    def move(self, ctx: StrategyContext) -> Move:
        """Cooperate half the time."""
        return Move.COOPERATE if ctx.roll < 0.5 else Move.DEFECT


class Opportunist:
    """Trait-driven: defects when greed, dishonesty and advantage line up.

    The only strategy that reads the agent rather than the history, which is
    what makes a personality visible in the game as well as in the walking.
    """

    name: StrategyName = "Opportunist"
    threshold = 0.22

    def move(self, ctx: StrategyContext) -> Move:
        """Defect when the opportunity is good enough to be worth it."""
        advantage = max(0.0, ctx.advantage)
        temptation = ctx.greed * (1.0 - ctx.honesty) * (0.35 + 0.65 * advantage)
        # Someone we trust gets the benefit of the doubt.
        temptation *= 1.0 - max(0.0, ctx.trust) * 0.5
        return Move.DEFECT if temptation > self.threshold else Move.COOPERATE


class LLMStrategy:
    """Placeholder for an LLM-decided move; falls back to Tit-for-Tat.

    Phase 5 replaces the body with the agent's deliberated choice. Until then
    it must still be a competent player, or LLM agents would be free food.
    """

    name: StrategyName = "LLM"

    def __init__(self) -> None:
        self._fallback = TitForTat()

    def move(self, ctx: StrategyContext) -> Move:
        """Defer to Tit-for-Tat until Phase 5 wires the gateway in."""
        return self._fallback.move(ctx)


class StrategyRegistry:
    """Name -> strategy lookup."""

    __slots__ = ("_strategies",)

    def __init__(self) -> None:
        self._strategies: dict[StrategyName, Strategy] = {}

    def __len__(self) -> int:
        return len(self._strategies)

    def __contains__(self, name: object) -> bool:
        return name in self._strategies

    def register(self, strategy: Strategy) -> None:
        """Register `strategy` under its name."""
        if strategy.name in self._strategies:
            msg = f"duplicate strategy: {strategy.name}"
            raise ValueError(msg)
        self._strategies[strategy.name] = strategy

    def get(self, name: StrategyName) -> Strategy | None:
        """Return the strategy called `name`, or `None`."""
        return self._strategies.get(name)

    def require(self, name: StrategyName) -> Strategy:
        """Return the strategy called `name`, falling back to Tit-for-Tat."""
        return self._strategies.get(name) or self._strategies["TitForTat"]

    @property
    def names(self) -> tuple[StrategyName, ...]:
        """Registered strategy names, sorted."""
        return tuple(sorted(self._strategies))


def build_strategy_registry() -> StrategyRegistry:
    """Return a registry holding every strategy in SPEC 5.2."""
    registry = StrategyRegistry()
    for strategy in (
        AlwaysCooperate(),
        AlwaysDefect(),
        TitForTat(),
        GenerousTitForTat(),
        Grudger(),
        Pavlov(),
        Detective(),
        RandomStrategy(),
        Opportunist(),
        LLMStrategy(),
    ):
        registry.register(strategy)
    return registry
