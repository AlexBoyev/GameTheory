"""Rate limiting, caching and back-pressure for LLM calls (SPEC section 7.5).

Every limit here exists to keep a local model from becoming the simulation's
bottleneck: the engine never waits, so the worst case is fewer deliberate
agents, never a slower world.
"""

import asyncio
import time
from collections import OrderedDict, deque
from dataclasses import dataclass

import structlog

from app.ai.llm.provider import LLMError, LLMProvider
from app.ai.llm.schemas import LLMRequest, LLMResponse
from app.ai.llm.telemetry import CircuitBreaker, Telemetry
from app.core.settings import HighSpeedPolicy, Settings

LOG = structlog.get_logger(__name__)

RATE_WINDOW_S = 60.0


@dataclass(slots=True)
class SchedulerLimits:
    """Runtime-tunable limits (`PUT /api/llm/settings`)."""

    max_agents: int = 8
    max_concurrency: int = 1
    max_calls_per_min: int = 30
    min_interval_sim_s: float = 20.0
    timeout_s: float = 20.0
    cache_size: int = 256
    high_speed_policy: HighSpeedPolicy = "reduced"
    high_speed_threshold: float = 5.0

    @classmethod
    def from_settings(cls, settings: Settings) -> "SchedulerLimits":
        """Build limits from application settings."""
        return cls(
            max_agents=settings.llm_max_agents,
            max_concurrency=settings.llm_max_concurrency,
            max_calls_per_min=settings.llm_max_calls_per_min,
            min_interval_sim_s=settings.llm_min_interval_sim_s,
            timeout_s=settings.llm_timeout_s,
            cache_size=settings.llm_cache_size,
            high_speed_policy=settings.llm_high_speed_policy,
        )

    def interval_for_speed(self, speed: float) -> float | None:
        """Return the per-agent interval at `speed`, or `None` to skip calls."""
        if speed < 0 or speed > self.high_speed_threshold:
            match self.high_speed_policy:
                case "off":
                    return None
                case "reduced":
                    return self.min_interval_sim_s * 4.0
                case "full":
                    return self.min_interval_sim_s
        return self.min_interval_sim_s


class LLMScheduler:
    """Queues requests, enforces limits, serves the LRU cache.

    `submit` never raises and never blocks the caller for longer than
    `limits.timeout_s`: a failed call comes back as an `LLMResponse` carrying
    `error`, because every caller's correct response to a failure is the same -
    carry on with utility AI.
    """

    __slots__ = (
        "_cache",
        "_calls",
        "_inflight",
        "_provider",
        "_semaphore",
        "_semaphore_size",
        "breaker",
        "limits",
        "telemetry",
    )

    def __init__(
        self,
        provider: LLMProvider,
        limits: SchedulerLimits,
        telemetry: Telemetry | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._provider = provider
        self.limits = limits
        self.telemetry = telemetry or Telemetry()
        self.breaker = breaker or CircuitBreaker(threshold=3, cooldown_s=60.0)
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._calls: deque[float] = deque()
        self._inflight = 0
        self._semaphore_size = max(1, limits.max_concurrency)
        self._semaphore = asyncio.Semaphore(self._semaphore_size)

    @property
    def provider(self) -> LLMProvider:
        """The provider currently in use."""
        return self._provider

    @property
    def queue_depth(self) -> int:
        """Requests currently waiting on the concurrency gate or in flight."""
        return self._inflight

    def set_provider(self, provider: LLMProvider) -> None:
        """Swap the provider at runtime and close the breaker."""
        self._provider = provider
        self.breaker.reset()
        self._cache.clear()

    def apply_limits(self, limits: SchedulerLimits) -> None:
        """Replace the limits, resizing the concurrency gate if it changed."""
        self.limits = limits
        if max(1, limits.max_concurrency) != self._semaphore_size:
            # Only safe because a new gate affects admissions from here on;
            # calls already in flight finish against the old one.
            self._semaphore_size = max(1, limits.max_concurrency)
            self._semaphore = asyncio.Semaphore(self._semaphore_size)
        while len(self._cache) > max(0, limits.cache_size):
            self._cache.popitem(last=False)

    # --------------------------------------------------------------- limits

    def _cached(self, key: str) -> str | None:
        """Look `key` up, refreshing its recency."""
        if not key or key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def _store(self, key: str, content: str) -> None:
        """Cache `content` under `key`, evicting the least recently used."""
        if not key or self.limits.cache_size <= 0:
            return
        self._cache[key] = content
        self._cache.move_to_end(key)
        while len(self._cache) > self.limits.cache_size:
            self._cache.popitem(last=False)

    def _rate_limited(self, now: float) -> bool:
        """Whether the calls-per-minute budget is spent."""
        while self._calls and now - self._calls[0] >= RATE_WINDOW_S:
            self._calls.popleft()
        return len(self._calls) >= self.limits.max_calls_per_min

    def _refuse(self, request: LLMRequest, reason: str) -> LLMResponse:
        """A response saying why no call was made, counted as a refusal.

        Visible in the monitor, but never as a provider failure: an open
        circuit or a spent budget is our own limit doing its job.
        """
        response = LLMResponse(
            agent_id=request.agent_id,
            kind=request.kind,
            model=self._provider.model,
            provider=self._provider.name,
            error=reason,
        )
        self.telemetry.refused(response, reason)
        return response

    # ---------------------------------------------------------------- submit

    async def submit(self, request: LLMRequest) -> LLMResponse:
        """Queue `request` and return its response when it completes."""
        cached = self._cached(request.cache_key)
        if cached is not None:
            response = LLMResponse(
                agent_id=request.agent_id,
                kind=request.kind,
                content=cached,
                model=self._provider.model,
                provider=self._provider.name,
                cached=True,
            )
            self.telemetry.record(response, request.prompt)
            return response

        if self.breaker.is_open(request.issued_sim_s):
            return self._refuse(request, "circuit open")

        now = time.monotonic()
        if self._rate_limited(now):
            # Not an error worth opening the breaker for: it is the limit
            # doing its job, so it must not count as a provider failure.
            return self._refuse(request, "rate limited")

        self._calls.append(now)
        self._inflight += 1
        try:
            async with self._semaphore:
                response = await self._call(request)
        finally:
            self._inflight -= 1

        if response.ok:
            self.breaker.on_success()
            self._store(request.cache_key, response.content)
        else:
            self.breaker.on_failure(request.issued_sim_s)
            if self.breaker.is_open(request.issued_sim_s):
                LOG.warning(
                    "llm.circuit_open",
                    provider=self._provider.name,
                    failures=self.breaker.consecutive_failures,
                )

        self.telemetry.record(response, request.prompt)
        return response

    async def _call(self, request: LLMRequest) -> LLMResponse:
        """One provider call, with the timeout and errors turned into data."""
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.limits.timeout_s):
                return await self._provider.generate(request)
        except TimeoutError:
            error = f"timeout after {self.limits.timeout_s}s"
        except LLMError as failure:
            error = str(failure)
        except asyncio.CancelledError:
            # Shutdown, not a provider fault - propagate without recording.
            raise
        except Exception as failure:
            error = f"{type(failure).__name__}: {failure}"
            LOG.warning("llm.provider_error", provider=self._provider.name, error=error)

        return LLMResponse(
            agent_id=request.agent_id,
            kind=request.kind,
            model=self._provider.model,
            provider=self._provider.name,
            latency_s=round(time.monotonic() - started, 4),
            error=error,
        )
