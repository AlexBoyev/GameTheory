"""`LLMGateway` - the single door between the simulation and any model.

Nothing outside this package may talk to a model, and nothing inside the
simulation may await one (CLAUDE.md architecture rules 1 and 3).
"""

from dataclasses import dataclass

from app.ai.llm.mock_provider import MockProvider
from app.ai.llm.provider import LLMProvider
from app.ai.llm.scheduler import LLMScheduler, SchedulerLimits
from app.ai.llm.schemas import Intention
from app.ai.llm.telemetry import LLMStats, Telemetry
from app.core.settings import LlmProviderName, Settings


@dataclass(frozen=True, slots=True)
class LLMStatus:
    """What `GET /api/llm/status` and the health endpoint report.

    Attributes:
        enabled: Whether deliberation is switched on at all.
        provider: Active provider name.
        model: Active model identifier.
        reachable: Last known reachability; `None` before the first check.
        circuit_open: True while the breaker is suppressing calls.
        queue_depth: Requests waiting.
        max_agents: How many agents may have LLM minds.
        fallback_active: True when the configured provider was swapped for mock.
    """

    enabled: bool
    provider: str
    model: str
    reachable: bool | None
    circuit_open: bool
    queue_depth: int
    max_agents: int
    fallback_active: bool


class LLMGateway:
    """Owns the provider, the scheduler and the fallback decision."""

    __slots__ = ("_configured", "_enabled", "_fallback", "_reachable", "_scheduler")

    def __init__(self, settings: Settings, provider: LLMProvider | None = None) -> None:
        self._configured: LlmProviderName = settings.llm_provider
        self._enabled = settings.llm_enabled
        self._fallback = provider is None and settings.llm_provider != "mock"
        resolved = provider or MockProvider()
        self._scheduler = LLMScheduler(resolved, SchedulerLimits.from_settings(settings))
        self._reachable: bool | None = None if self._fallback else True

    @property
    def scheduler(self) -> LLMScheduler:
        """The scheduler enforcing rate limits."""
        return self._scheduler

    @property
    def enabled(self) -> bool:
        """Whether deliberation is switched on."""
        return self._enabled

    def status(self) -> LLMStatus:
        """Return current status without touching the network."""
        provider = self._scheduler.provider
        return LLMStatus(
            enabled=self._enabled,
            provider=provider.name,
            model=provider.model,
            reachable=self._reachable,
            circuit_open=self._scheduler.breaker.opened_at_s is not None,
            queue_depth=self._scheduler.queue_depth,
            max_agents=self._scheduler.limits.max_agents,
            fallback_active=self._fallback,
        )

    def stats(self) -> LLMStats:
        """Return call counters."""
        return self._scheduler.telemetry.stats

    def telemetry(self) -> Telemetry:
        """Return the call log."""
        return self._scheduler.telemetry

    async def check_health(self) -> bool:
        """Probe the provider and cache the result."""
        self._reachable = await self._scheduler.provider.healthy()
        return self._reachable

    def set_enabled(self, enabled: bool) -> None:
        """Switch deliberation on or off at runtime."""
        self._enabled = enabled

    async def request_intention(self, agent_id: int, prompt: str) -> Intention | None:
        """Queue a deliberation for `agent_id`. Implemented in Phase 5."""
        msg = "LLMGateway.request_intention() arrives in Phase 5 (LLM minds)"
        raise NotImplementedError(msg)

    async def aclose(self) -> None:
        """Release provider resources."""
        await self._scheduler.provider.aclose()
