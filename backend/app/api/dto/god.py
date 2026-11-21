"""God-tool DTOs (SPEC section 9.4). Behaviour arrives in Phase 6."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GodAction(StrEnum):
    """Supported interventions, used as the `POST /api/god/{action}` path."""

    DROP_FOOD = "drop_food"
    DROUGHT = "drought"
    PLAGUE = "plague"
    BOUNTY = "bounty"
    SPAWN_AGENT = "spawn_agent"
    SMITE = "smite"


class GodActionRequest(BaseModel):
    """Parameters for an intervention; which fields matter depends on the action."""

    model_config = ConfigDict(extra="forbid")

    x: float | None = Field(default=None, description="World x, where the action is local.")
    z: float | None = Field(default=None, description="World z, where the action is local.")
    radius: float | None = Field(default=None, gt=0.0)
    amount: float | None = Field(default=None, description="Food dropped, severity, etc.")
    agent_id: int | None = Field(default=None, description="Target for smite.")
    strategy: str | None = Field(default=None, description="Strategy for spawn_agent.")
    brain_type: str | None = Field(default=None, description="utility | llm for spawn_agent.")


class GodActionResultDTO(BaseModel):
    """What the intervention did."""

    model_config = ConfigDict(extra="forbid")

    action: GodAction
    affected: int = 0
    detail: str = ""
