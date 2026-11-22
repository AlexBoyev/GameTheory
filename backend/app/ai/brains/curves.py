"""Response curves: how a raw input is shaped before it is weighted.

Their own module because both ends of the utility system need them - the
brain, and the `Consideration` type the skills build - and `utility_brain`
imports `skills.base`, so `skills.base` cannot import it back.
"""

import math
from enum import StrEnum


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
