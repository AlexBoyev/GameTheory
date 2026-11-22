"""Running tallies of what the society is doing (SPEC section 10).

The metrics service samples this; the encounter resolver and the social
skills feed it. Counters are cumulative, so a chart can show either the
running total or the difference between two samples.
"""

from collections import Counter
from dataclasses import dataclass, field, fields
from typing import Any

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
        """Reset every tally; called when the world is rebuilt.

        Derived from the dataclass fields rather than listing them, because
        listing them is a trap: `coup_attempts` was added and this method was
        not updated, so one world's attempted coups leaked into the next.
        """
        for spec in fields(self):
            value = getattr(self, spec.name)
            if isinstance(value, Counter | dict):
                value.clear()
            else:
                setattr(self, spec.name, 0)

    def to_dict(self) -> dict[str, Any]:
        """Serialise every tally, for a snapshot (SPEC 11)."""
        payload: dict[str, Any] = {}
        for spec in fields(self):
            value = getattr(self, spec.name)
            payload[spec.name] = dict(value) if isinstance(value, Counter | dict) else value
        return payload

    def load(self, payload: dict[str, Any]) -> None:
        """Restore tallies from `to_dict` output, ignoring anything unknown.

        Unknown keys are skipped rather than rejected: a snapshot taken before
        a counter existed should still load, just without that counter.
        """
        for spec in fields(self):
            if spec.name not in payload:
                continue
            incoming = payload[spec.name]
            current = getattr(self, spec.name)
            if isinstance(current, Counter):
                current.clear()
                current.update({str(key): int(count) for key, count in incoming.items()})
            elif isinstance(current, dict):
                current.clear()
                current.update({str(key): float(value) for key, value in incoming.items()})
            else:
                setattr(self, spec.name, int(incoming))
