"""Rate limiting, caching and back-pressure for LLM calls (SPEC section 7.5).

Every limit here exists to keep a local model from becoming the simulation's
bottleneck: the engine never waits, so the worst case is fewer deliberate
agents, never a slower world. Implemented in Phase 5.
"""

from dataclasses import dataclass

from app.ai.llm.provider import LLMProvider
from app.ai.llm.schemas import LLMRequest, LLMResponse
from app.ai.llm.telemetry import CircuitBreaker, Telemetry
from app.core.settings import HighSpeedPolicy, Settings


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
    """Queues requests, enforces limits, serves the LRU cache."""

    __slots__ = ("_provider", "breaker", "limits", "telemetry")

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

    @property
    def provider(self) -> LLMProvider:
        """The provider currently in use."""
        return self._provider

    @property
    def queue_depth(self) -> int:
        """Pending requests. Always 0 until Phase 5 adds the queue."""
        return 0

    def set_provider(self, provider: LLMProvider) -> None:
        """Swap the provider at runtime and close the breaker."""
        self._provider = provider
        self.breaker.reset()

    async def submit(self, request: LLMRequest) -> LLMResponse:
        """Queue `request` and return its response when it completes."""
        msg = "LLMScheduler.submit() arrives in Phase 5 (LLM minds)"
        raise NotImplementedError(msg)
