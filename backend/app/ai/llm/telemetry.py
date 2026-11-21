"""Call log and aggregate stats behind `GET /api/llm/stats`."""

from collections import deque
from dataclasses import dataclass, field

from app.ai.llm.schemas import LLMResponse


@dataclass(frozen=True, slots=True)
class CallRecord:
    """One finished call, kept for the LLM monitor panel."""

    agent_id: int
    kind: str
    provider: str
    model: str
    latency_s: float
    cached: bool
    ok: bool
    error: str | None = None
    prompt_preview: str = ""
    response_preview: str = ""


@dataclass(slots=True)
class LLMStats:
    """Counters since process start."""

    calls: int = 0
    failures: int = 0
    cache_hits: int = 0
    timeouts: int = 0
    refusals: int = 0
    """Requests the scheduler declined to make - rate limit or open circuit.

    Counted separately from `failures` because nothing is wrong with the
    provider: these are our own limits working. They were invisible at first,
    which made the monitor under-report what the layer was doing (a run showed
    50 calls where 100 had been asked for).
    """
    total_latency_s: float = 0.0
    prompt_tokens_estimate: int = 0

    @property
    def avg_latency_s(self) -> float:
        """Mean latency over non-cached calls (0.0 before the first call)."""
        billed = self.calls - self.cache_hits
        return self.total_latency_s / billed if billed > 0 else 0.0

    @property
    def failure_rate(self) -> float:
        """Share of attempted calls that failed, in `[0, 1]`."""
        return self.failures / self.calls if self.calls else 0.0

    @property
    def requested(self) -> int:
        """Everything asked for, including what was refused before going out."""
        return self.calls + self.refusals


class Telemetry:
    """Keeps the last N call records plus running totals."""

    __slots__ = ("_records", "stats")

    def __init__(self, capacity: int = 50) -> None:
        self._records: deque[CallRecord] = deque(maxlen=capacity)
        self.stats = LLMStats()

    @property
    def recent(self) -> list[CallRecord]:
        """Most recent calls, newest first."""
        return list(reversed(self._records))

    def refused(self, response: LLMResponse, reason: str) -> None:
        """Record a request the scheduler declined to send."""
        self.stats.refusals += 1
        self._records.append(
            CallRecord(
                agent_id=response.agent_id,
                kind=response.kind,
                provider=response.provider,
                model=response.model,
                latency_s=0.0,
                cached=False,
                ok=False,
                error=reason,
            )
        )

    def record(self, response: LLMResponse, prompt_preview: str = "") -> None:
        """Fold `response` into the stats and append a record."""
        self.stats.calls += 1
        self.stats.prompt_tokens_estimate += response.prompt_tokens_estimate
        if response.cached:
            self.stats.cache_hits += 1
        else:
            self.stats.total_latency_s += response.latency_s
        if not response.ok:
            self.stats.failures += 1
            if response.error and "timeout" in response.error.lower():
                self.stats.timeouts += 1
        self._records.append(
            CallRecord(
                agent_id=response.agent_id,
                kind=response.kind,
                provider=response.provider,
                model=response.model,
                latency_s=response.latency_s,
                cached=response.cached,
                ok=response.ok,
                error=response.error,
                prompt_preview=prompt_preview[:400],
                response_preview=response.content[:400],
            )
        )


@dataclass(slots=True)
class CircuitBreaker:
    """Opens after `threshold` consecutive failures, closes after a cooldown.

    Cooldown is measured in sim-seconds supplied by the caller, so the breaker
    inherits the simulation's clock instead of reading the wall clock.
    """

    threshold: int = 3
    cooldown_s: float = 60.0
    consecutive_failures: int = 0
    opened_at_s: float | None = field(default=None)

    def is_open(self, now_s: float) -> bool:
        """True while calls should be suppressed."""
        if self.opened_at_s is None:
            return False
        if now_s - self.opened_at_s >= self.cooldown_s:
            self.reset()
            return False
        return True

    def on_success(self) -> None:
        """Record a success, closing the breaker."""
        self.reset()

    def on_failure(self, now_s: float) -> None:
        """Record a failure, opening the breaker at the threshold."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold:
            self.opened_at_s = now_s

    def reset(self) -> None:
        """Close the breaker and clear the failure streak."""
        self.consecutive_failures = 0
        self.opened_at_s = None
