"""LLM status, stats and runtime settings (SPEC sections 7.5, 8).

Status and stats are live so the UI can say "mock provider, Ollama not
installed" honestly rather than pretending deliberation is happening.
"""

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.api.dto.llm import LLMCallDTO, LLMSettingsRequest, LLMStatsDTO, LLMStatusDTO
from app.container import Container

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/status", response_model=LLMStatusDTO, summary="Provider and circuit status")
def status(container: ContainerDep) -> LLMStatusDTO:
    """Return the gateway's current provider, model and health."""
    current = container.gateway.status()
    return LLMStatusDTO(
        enabled=current.enabled,
        provider=current.provider,
        model=current.model,
        reachable=current.reachable,
        circuit_open=current.circuit_open,
        queue_depth=current.queue_depth,
        max_agents=current.max_agents,
        fallback_active=current.fallback_active,
        high_speed_policy=current.high_speed_policy,
        min_interval_sim_s=current.min_interval_sim_s,
    )


@router.get("/stats", response_model=LLMStatsDTO, summary="Call counters and recent calls")
def stats(container: ContainerDep) -> LLMStatsDTO:
    """Return call counts, latency and the recent call log."""
    counters = container.gateway.stats()
    return LLMStatsDTO(
        calls=counters.calls,
        failures=counters.failures,
        cache_hits=counters.cache_hits,
        timeouts=counters.timeouts,
        refusals=counters.refusals,
        avg_latency_s=counters.avg_latency_s,
        failure_rate=counters.failure_rate,
        prompt_tokens_estimate=counters.prompt_tokens_estimate,
        recent=[
            LLMCallDTO(
                agent_id=record.agent_id,
                kind=record.kind,
                provider=record.provider,
                model=record.model,
                latency_s=record.latency_s,
                cached=record.cached,
                ok=record.ok,
                error=record.error,
                prompt_preview=record.prompt_preview,
                response_preview=record.response_preview,
            )
            for record in container.gateway.telemetry().recent
        ],
    )


def _status_dto(container: Container) -> LLMStatusDTO:
    """Current gateway status as the wire DTO."""
    current = container.gateway.status()
    return LLMStatusDTO(
        enabled=current.enabled,
        provider=current.provider,
        model=current.model,
        reachable=current.reachable,
        circuit_open=current.circuit_open,
        queue_depth=current.queue_depth,
        max_agents=current.max_agents,
        fallback_active=current.fallback_active,
        high_speed_policy=current.high_speed_policy,
        min_interval_sim_s=current.min_interval_sim_s,
    )


@router.put("/settings", response_model=LLMStatusDTO, summary="Change LLM settings")
async def put_settings(request: LLMSettingsRequest, container: ContainerDep) -> LLMStatusDTO:
    """Update provider, model and rate limits at runtime.

    Switching to Ollama when it is not running is allowed and reported, not
    refused: `reachable: false` in the reply is the honest answer, and the
    simulation carries on with utility AI either way.
    """
    gateway = container.gateway
    if request.enabled is not None:
        gateway.set_enabled(request.enabled)

    limits = {
        name: value
        for name, value in (
            ("max_agents", request.max_agents),
            ("max_concurrency", request.max_concurrency),
            ("max_calls_per_min", request.max_calls_per_min),
            ("min_interval_sim_s", request.min_interval_sim_s),
            ("timeout_s", request.timeout_s),
            ("high_speed_policy", request.high_speed_policy),
        )
        if value is not None
    }
    if limits:
        gateway.set_limits(**limits)

    if request.provider is not None or request.model is not None:
        current = gateway.status()
        name = request.provider or ("ollama" if current.provider == "ollama" else "mock")
        model = request.model or (
            container.settings.ollama_model if name == "ollama" else "mock-deterministic"
        )
        await gateway.switch(name, model)

    return _status_dto(container)
