"""Running tallies of what the society is doing (SPEC section 10).

The metrics service samples this; the encounter resolver and the social
skills feed it. Counters are cumulative, so a chart can show either the
running total or the difference between two samples.
"""

from collections import Counter
from dataclasses import dataclass, field

from app.ai.gametheory.encounters import EncounterResult, GameKind
from app.core.world_config import StrategyName


@dataclass(slots=True)
class SocialLedger:
    """Cumulative counts of every socially interesting thing that happened."""

    cooperations: Counter[str] = field(default_factory=Counter)
    defections: Counter[str] = field(default_factory=Counter)
    rounds: Counter[str] = field(default_factory=Counter)
    payoff_by_strategy: dict[str, float] = field(default_factory=dict)
    rounds_by_strategy: Counter[str] = field(default_factory=Counter)

    betrayals: int = 0
    gifts: int = 0
    trades: int = 0
    attacks: int = 0
    lies_told: int = 0
    lies_caught: int = 0
    gossip_spread: int = 0
    alliances: int = 0
    shelters_built: int = 0
    births: int = 0
    tribes_founded: int = 0
    wars_declared: int = 0
    peace_made: int = 0
    coups: int = 0
    """Coups that actually changed a leader."""

    coup_attempts: int = 0
    """Every challenge, won or lost. Most challenges lose, so reporting only
    the wins made the charts read "coups: 0" in a world full of plotting."""

    def record_encounter(
        self,
        result: EncounterResult,
        strategy_a: StrategyName,
        strategy_b: StrategyName,
    ) -> None:
        """Fold one resolved encounter into the tallies."""
        game = result.game.value
        self.rounds[game] += 2
        self.cooperations[game] += result.cooperations
        self.defections[game] += 2 - result.cooperations
        self.betrayals += len(result.betrayal_by)

        for strategy, payoff in ((strategy_a, result.payoff_a), (strategy_b, result.payoff_b)):
            self.payoff_by_strategy[strategy] = self.payoff_by_strategy.get(strategy, 0.0) + payoff
            self.rounds_by_strategy[strategy] += 1

    def cooperation_rate(self, game: GameKind | None = None) -> float:
        """Share of moves that were cooperative, overall or for one game."""
        if game is None:
            played = sum(self.rounds.values())
            cooperative = sum(self.cooperations.values())
        else:
            played = self.rounds[game.value]
            cooperative = self.cooperations[game.value]
        return cooperative / played if played else 0.0

    def cooperation_rates(self) -> dict[str, float]:
        """Cooperation rate per game, for the charts panel."""
        return {
            game: self.cooperations[game] / played
            for game, played in self.rounds.items()
            if played > 0
        }

    def average_payoffs(self) -> dict[str, float]:
        """Mean payoff per strategy - which gene is actually winning."""
        return {
            strategy: self.payoff_by_strategy.get(strategy, 0.0) / rounds
            for strategy, rounds in self.rounds_by_strategy.items()
            if rounds > 0
        }

    def clear(self) -> None:
        """Reset every tally; called when the world is rebuilt."""
        self.cooperations.clear()
        self.defections.clear()
        self.rounds.clear()
        self.payoff_by_strategy.clear()
        self.rounds_by_strategy.clear()
        self.betrayals = 0
        self.gifts = 0
        self.trades = 0
        self.attacks = 0
        self.lies_told = 0
        self.lies_caught = 0
        self.gossip_spread = 0
        self.alliances = 0
        self.shelters_built = 0
        self.births = 0
        self.tribes_founded = 0
        self.wars_declared = 0
        self.peace_made = 0
        self.coups = 0
        self.coup_attempts = 0
