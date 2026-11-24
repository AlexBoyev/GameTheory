"""`LLMGateway` - the single door between the simulation and any model.

Nothing outside this package may talk to a model, and nothing inside the
simulation may await one (CLAUDE.md architecture rules 1 and 3).
"""

from dataclasses import dataclass, replace

from app.ai.llm.mock_provider import MockProvider
from app.ai.llm.ollama_provider import OllamaProvider
from app.ai.llm.provider import LLMProvider
from app.ai.llm.scheduler import LLMScheduler, SchedulerLimits
from app.ai.llm.telemetry import CircuitBreaker, LLMStats, Telemetry
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
        high_speed_policy: What happens to deliberation above the threshold.
        min_interval_sim_s: Minimum sim-seconds between one agent's calls.
    """

    enabled: bool
    provider: str
    model: str
    reachable: bool | None
    circuit_open: bool
    queue_depth: int
    max_agents: int
    fallback_active: bool
    high_speed_policy: str = "reduced"
    min_interval_sim_s: float = 20.0


class LLMGateway:
    """Owns the provider, the scheduler and the fallback decision."""

    __slots__ = (
        "_configured",
        "_enabled",
        "_fallback",
        "_ollama_url",
        "_reachable",
        "_scheduler",
    )

    def __init__(self, settings: Settings, provider: LLMProvider | None = None) -> None:
        self._configured: LlmProviderName = settings.llm_provider
        self._ollama_url = settings.ollama_url
        self._enabled = settings.llm_enabled
        self._fallback = provider is None and settings.llm_provider != "mock"
        resolved = provider or MockProvider()
        self._scheduler = LLMScheduler(
            resolved,
            SchedulerLimits.from_settings(settings),
            # Built here rather than defaulted inside the scheduler: the
            # scheduler's fallback repeated these two numbers, so setting
            # `LLM_CIRCUIT_FAILURES` or `LLM_CIRCUIT_COOLDOWN_S` changed
            # nothing and looked like it had.
            breaker=CircuitBreaker(
                threshold=settings.llm_circuit_failures,
                cooldown_s=settings.llm_circuit_cooldown_s,
            ),
        )
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
            high_speed_policy=self._scheduler.limits.high_speed_policy,
            min_interval_sim_s=self._scheduler.limits.min_interval_sim_s,
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

    def set_limits(self, **changes: object) -> None:
        """Apply runtime limit changes (`PUT /api/llm/settings`)."""
        limits = replace(self._scheduler.limits, **changes)  # type: ignore[arg-type]
        self._scheduler.apply_limits(limits)

    async def switch(self, provider: LlmProviderName, model: str) -> bool:
        """Point the gateway at `provider`/`model` and report reachability.

        Naming the provider rather than passing one in keeps `api/` free of
        any import from `ai/` (import-linter: "api/ talks to services, never
        to sim or ai internals").
        """
        built: LLMProvider = (
            OllamaProvider(
                base_url=self._ollama_url,
                model=model,
                timeout_s=self._scheduler.limits.timeout_s,
            )
            if provider == "ollama"
            else MockProvider(model=model)
        )
        self._configured = provider
        return await self.use_provider(built)

    async def use_provider(self, provider: LLMProvider) -> bool:
        """Switch providers at runtime and re-probe reachability.

        The old provider's transport is released: leaving an `AsyncClient`
        open for a provider nothing refers to leaks a connection pool for the
        life of the process.
        """
        previous = self._scheduler.provider
        self._scheduler.set_provider(provider)
        self._fallback = False
        if previous is not provider:
            await previous.aclose()
        return await self.check_health()

    async def aclose(self) -> None:
        """Release provider resources."""
        await self._scheduler.provider.aclose()
