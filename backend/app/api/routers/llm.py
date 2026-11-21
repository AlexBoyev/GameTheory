"""LLM status, stats and runtime settings (SPEC sections 7.5, 8).

Status and stats are live from Phase 1 so the UI can show "mock provider,
Ollama not installed" honestly. Mutating the settings lands in Phase 5.
"""

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.api.dto.llm import LLMCallDTO, LLMSettingsRequest, LLMStatsDTO, LLMStatusDTO
from app.api.errors import not_implemented_yet

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


@router.put("/settings", response_model=LLMStatusDTO, summary="Change LLM settings")
def put_settings(request: LLMSettingsRequest, container: ContainerDep) -> LLMStatusDTO:
    """Update provider, model and rate limits at runtime."""
    raise not_implemented_yet("Changing LLM settings", phase=5)
