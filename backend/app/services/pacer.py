"""The wall clock, kept out of `sim/`.

`sim.engine.Pacer` is a protocol; this is the only implementation that reads
real time, which is what lets the determinism contract be machine-checked.
"""

import time


class MonotonicPacer:
    """Real-time pacing for the engine thread."""

    __slots__ = ()

    def monotonic(self) -> float:
        """Seconds from an arbitrary monotonic origin."""
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        """Block the calling thread for `seconds` (no-op when not positive)."""
        if seconds > 0:
            time.sleep(seconds)


class FrozenPacer:
    """Deterministic pacer for tests: time only moves when `sleep` is called."""

    __slots__ = ("now",)

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        """Current fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance fake time without blocking."""
        self.now += max(0.0, seconds)
