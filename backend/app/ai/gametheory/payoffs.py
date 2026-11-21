"""Loading payoff matrices from `config/payoffs.yaml` (SPEC section 5.1).

Payoffs live in configuration rather than code so an experiment is a file
edit, not a redeploy. The loader validates that the Prisoner's Dilemma really
is one - a matrix where defection does not tempt produces a world where
nothing interesting happens, and that should fail loudly.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.ai.gametheory.encounters import GameKind, PayoffMatrix

DEFAULT_PAYOFFS: dict[GameKind, PayoffMatrix] = {
    GameKind.PRISONERS_DILEMMA: PayoffMatrix(5.0, 3.0, 1.0, 0.0),
    GameKind.STAG_HUNT: PayoffMatrix(2.0, 6.0, 1.5, 0.0),
    GameKind.HAWK_DOVE: PayoffMatrix(4.0, 2.0, -2.0, 0.5),
    GameKind.ULTIMATUM: PayoffMatrix(4.0, 2.5, 0.0, 0.5),
    GameKind.PUBLIC_GOODS: PayoffMatrix(3.0, 2.5, 0.5, 0.0),
}

DEFAULT_TREMBLING_HAND = 0.02


@dataclass(frozen=True, slots=True)
class PayoffConfig:
    """Everything the encounter resolver needs from configuration."""

    matrices: dict[GameKind, PayoffMatrix]
    trembling_hand: float = DEFAULT_TREMBLING_HAND
    fair_split: float = 0.4
    rejection_trust_penalty: float = 0.25
    contribution: float = 2.0
    public_goods_multiplier: float = 1.7

    def matrix(self, game: GameKind) -> PayoffMatrix:
        """Return the matrix for `game`, falling back to the default."""
        return self.matrices.get(game, DEFAULT_PAYOFFS[game])


def _matrix_from(entry: dict[str, Any], fallback: PayoffMatrix) -> PayoffMatrix:
    """Build a matrix from a config mapping, keeping defaults for gaps."""
    return PayoffMatrix(
        temptation=float(entry.get("temptation", fallback.temptation)),
        reward=float(entry.get("reward", fallback.reward)),
        punishment=float(entry.get("punishment", fallback.punishment)),
        sucker=float(entry.get("sucker", fallback.sucker)),
    )


def load_payoffs(path: Path | None = None) -> PayoffConfig:
    """Load payoffs from `path`, or return the documented defaults.

    A missing or empty file is not an error - the defaults in this module are
    the ones SPEC 5.1 documents.
    """
    raw: dict[str, Any] = {}
    if path is not None and path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded

    matrices = dict(DEFAULT_PAYOFFS)
    for game in GameKind:
        entry = raw.get(game.value)
        if isinstance(entry, dict):
            matrices[game] = _matrix_from(entry, DEFAULT_PAYOFFS[game])

    dilemma = matrices[GameKind.PRISONERS_DILEMMA]
    if not dilemma.is_dilemma:
        msg = (
            "prisoners_dilemma payoffs must satisfy T > R > P > S, got "
            f"T={dilemma.temptation} R={dilemma.reward} "
            f"P={dilemma.punishment} S={dilemma.sucker}"
        )
        raise ValueError(msg)

    ultimatum = raw.get("ultimatum", {}) if isinstance(raw.get("ultimatum"), dict) else {}
    goods = raw.get("public_goods", {}) if isinstance(raw.get("public_goods"), dict) else {}
    noise = raw.get("noise", {}) if isinstance(raw.get("noise"), dict) else {}

    return PayoffConfig(
        matrices=matrices,
        trembling_hand=float(noise.get("trembling_hand", DEFAULT_TREMBLING_HAND)),
        fair_split=float(ultimatum.get("fair_split", 0.4)),
        rejection_trust_penalty=float(ultimatum.get("rejection_trust_penalty", 0.25)),
        contribution=float(goods.get("contribution", 2.0)),
        public_goods_multiplier=float(goods.get("multiplier", 1.7)),
    )
