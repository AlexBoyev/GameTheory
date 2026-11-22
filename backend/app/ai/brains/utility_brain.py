"""Utility AI: response curves and softmax choice (SPEC 7.4).

Each skill computes its own `utility()` directly rather than composing
declarative considerations. `apply_curve` is the shared shaping function they
can use; the `Consideration` wrapper the SPEC implies was unused scaffolding
and has been removed. Adopting it across all 32 skills is a design decision,
not a cleanup - see docs/REVIEW.md.

Why softmax rather than "pick the best": two agents with the same needs but
different personalities should not behave identically, and a world where every
hungry agent walks to the same bush looks like a simulation of one agent. The
temperature is how much personality beats arithmetic.
"""

import math
from enum import StrEnum

from app.ai.brains.base import Decision, DecisionContext, ScoredOption
from app.ai.skills.base import Skill
from app.ai.skills.registry import SkillRegistry
from app.core.result import is_ok

MIN_SCORE = 1e-4
"""Below this a skill is treated as "not worth doing"."""


class Curve(StrEnum):
    """Response curve shapes applied to a normalised input."""

    LINEAR = "linear"
    QUADRATIC = "quadratic"
    INVERSE = "inverse"
    LOGISTIC = "logistic"
    STEP = "step"


def apply_curve(curve: Curve, value: float) -> float:
    """Map `value` in `[0, 1]` through `curve`, result clamped to `[0, 1]`."""
    clamped = min(1.0, max(0.0, value))
    match curve:
        case Curve.LINEAR:
            return clamped
        case Curve.QUADRATIC:
            return clamped * clamped
        case Curve.INVERSE:
            return 1.0 - clamped
        case Curve.LOGISTIC:
            return 1.0 / (1.0 + math.exp(-12.0 * (clamped - 0.5)))
        case Curve.STEP:
            return 1.0 if clamped >= 0.5 else 0.0


class UtilityBrain:
    """Scores every runnable skill and samples from the top options."""

    name = "utility"

    __slots__ = ("_registry", "temperature", "top_k")

    def __init__(self, registry: SkillRegistry, temperature: float = 0.35, top_k: int = 3) -> None:
        self._registry = registry
        self.temperature = max(1e-3, temperature)
        self.top_k = max(1, top_k)

    def decide(self, ctx: DecisionContext) -> Decision:
        """Return the chosen skill plus the top-K trace."""
        scored = self._score_all(ctx)
        if not scored:
            return Decision(skill="", reason="nothing is possible right now")

        shortlist = scored[: self.top_k]
        chosen_index = self._sample(shortlist, ctx)
        chosen_skill = shortlist[chosen_index][0]

        options = tuple(
            ScoredOption(
                skill=type(skill).name,
                score=round(score, 4),
                reason=f"{type(skill).category.value} need",
            )
            for skill, score in shortlist
        )
        return Decision(
            skill=type(chosen_skill).name,
            options=options,
            reason=self._explain(shortlist, chosen_index),
            from_intention=type(chosen_skill).name in ctx.intention_skills,
        )

    def _score_all(self, ctx: DecisionContext) -> list[tuple[Skill, float]]:
        """Return runnable skills with scores, best first, ties broken by name."""
        scored: list[tuple[Skill, float]] = []

        for skill in self._registry.all():
            definition = type(skill)
            if not definition.autonomous or definition.name in ctx.unavailable:
                continue
            # Skip what cannot possibly run before paying for `check()` and
            # `utility()`. Each requirement is a cheap pre-test of something
            # `check()` already enforces (see `Requirement`), so this changes
            # the cost and never the outcome.
            if not definition.requires.issubset(ctx.facts):
                continue
            params = definition.Params()
            if not is_ok(skill.check(ctx.agent, ctx.world, params)):
                continue

            score = skill.utility(ctx.agent, ctx)
            if definition.name in ctx.intention_skills:
                score += ctx.intention_bonus
            if definition.name == ctx.current_skill:
                score += ctx.commitment_bonus
            if score > MIN_SCORE:
                scored.append((skill, score))

        scored.sort(key=lambda entry: (-entry[1], type(entry[0]).name))
        return scored

    def _sample(self, shortlist: list[tuple[Skill, float]], ctx: DecisionContext) -> int:
        """Pick an index from `shortlist` by softmax over the scores."""
        if len(shortlist) == 1:
            return 0
        best = shortlist[0][1]
        weights = [math.exp((score - best) / self.temperature) for _, score in shortlist]
        total = sum(weights)
        roll = float(ctx.world.rngs["decide"].random()) * total
        cumulative = 0.0
        for index, weight in enumerate(weights):
            cumulative += weight
            if roll <= cumulative:
                return index
        return len(shortlist) - 1

    @staticmethod
    def _explain(shortlist: list[tuple[Skill, float]], chosen_index: int) -> str:
        """Return a one-line reason for the inspector and the agent's thought.

        Softmax means the top option does not always win, so the wording has
        to distinguish the two cases - "Flee (0.34) over Gather (0.49)" reads
        as though 0.34 beat 0.49, which is exactly backwards.
        """
        chosen, score = shortlist[chosen_index]
        name = type(chosen).name
        if len(shortlist) == 1:
            return f"{name} ({score:.2f}) was the only option"

        if chosen_index == 0:
            rival, rival_score = shortlist[1]
            return f"{name} ({score:.2f}) over {type(rival).name} ({rival_score:.2f})"

        best, best_score = shortlist[0]
        return f"{name} ({score:.2f}) on a whim, passing up {type(best).name} ({best_score:.2f})"
