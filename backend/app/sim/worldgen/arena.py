"""The tournament arena: a ring of contestants (SPEC section 5.3).

In `sim/` because placing agents is world generation, and because `sim/` may
not import `ai/` - the tournament system reads this, not the other way round.
"""

import math

RING_RADIUS_FRACTION = 0.34
"""Where the ring sits, as a fraction of the world extent."""


def ring_positions(count: int, extent: float) -> list[tuple[float, float]]:
    """Evenly spaced positions on a circle centred on the origin.

    A tournament's pairings are scheduled rather than spatial, so the ring is
    purely so you can see who is playing - but it has to be a *ring*, because
    a crowd in the middle would look like the island and read like a bug.
    """
    radius = extent * RING_RADIUS_FRACTION
    return [
        (
            radius * math.cos(2.0 * math.pi * index / max(1, count)),
            radius * math.sin(2.0 * math.pi * index / max(1, count)),
        )
        for index in range(count)
    ]
