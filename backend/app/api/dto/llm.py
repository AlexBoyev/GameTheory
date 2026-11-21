"""LLM control and monitoring DTOs (SPEC sections 7.5, 8)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMStatusDTO(BaseModel):
    """`GET /api/llm/status`."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    provider: str
    model: str
    reachable: bool | None = None
    circuit_open: bool = False
    queue_depth: int = 0
    max_agents: int = 0
    fallback_active: bool = Field(
        default=False,
        description="True when Ollama was requested but mock is serving instead.",
    )
    high_speed_policy: str = Field(
        default="reduced",
        description="What happens to deliberation above the speed threshold.",
    )
    min_interval_sim_s: float = Field(
        default=20.0,
        description="Minimum sim-seconds between one agent's deliberations.",
    )


class LLMCallDTO(BaseModel):
    """One row of the LLM monitor's call log."""

    model_config = ConfigDict(extra="forbid")

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


class LLMStatsDTO(BaseModel):
    """`GET /api/llm/stats`."""

    model_config = ConfigDict(extra="forbid")

    calls: int = 0
    failures: int = 0
    cache_hits: int = 0
    timeouts: int = 0
    refusals: int = 0
    avg_latency_s: float = 0.0
    failure_rate: float = 0.0
    prompt_tokens_estimate: int = 0
    recent: list[LLMCallDTO] = Field(default_factory=list)


class LLMSettingsRequest(BaseModel):
    """`PUT /api/llm/settings`. Omitted fields are left unchanged."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    provider: Literal["mock", "ollama"] | None = None
    model: str | None = None
    max_agents: int | None = Field(default=None, ge=0, le=64)
    max_concurrency: int | None = Field(default=None, ge=1, le=8)
    max_calls_per_min: int | None = Field(default=None, ge=1, le=600)
    min_interval_sim_s: float | None = Field(default=None, ge=0.0)
    timeout_s: float | None = Field(default=None, gt=0.0, le=120.0)
    high_speed_policy: Literal["off", "reduced", "full"] | None = None
