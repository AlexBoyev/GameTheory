"""Shared response shapes."""

from pydantic import BaseModel, ConfigDict, Field


class LLMHealthDTO(BaseModel):
    """LLM summary embedded in the health response."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    provider: str
    model: str
    reachable: bool | None = Field(default=None, description="None = not probed yet.")
    circuit_open: bool = False
    fallback_active: bool = False


class HealthDTO(BaseModel):
    """`GET /api/health`: liveness plus LLM status."""

    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    app: str
    version: str
    env: str
    llm: LLMHealthDTO


class AckDTO(BaseModel):
    """Generic acknowledgement for commands with nothing to return."""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    detail: str = ""
