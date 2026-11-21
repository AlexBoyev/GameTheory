"""Agent and tribe DTOs for the inspector and overlays (SPEC sections 4, 6, 9.4)."""

from pydantic import BaseModel, ConfigDict, Field


class NeedsDTO(BaseModel):
    """Drives, 0-100."""

    model_config = ConfigDict(extra="forbid")

    hunger: float
    thirst: float
    energy: float
    safety: float
    social: float


class TraitsDTO(BaseModel):
    """Personality, 0-1."""

    model_config = ConfigDict(extra="forbid")

    aggression: float
    honesty: float
    loyalty: float
    greed: float
    sociability: float
    cunning: float
    courage: float
    charisma: float


class AgentSummaryDTO(BaseModel):
    """One row of `GET /api/agents`."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    x: float
    z: float
    state: str
    strategy: str
    brain_type: str
    tribe_id: int | None = None
    role: str = "none"
    health: float = 100.0
    alive: bool = True


class RelationshipDTO(BaseModel):
    """One entry in the inspector's relationships list."""

    model_config = ConfigDict(extra="forbid")

    other_id: int
    other_name: str = ""
    trust: float = Field(ge=-1.0, le=1.0)
    reputation: float = 0.0
    interactions: int = 0
    is_ally: bool = False
    caught_lying: int = 0


class DecisionOptionDTO(BaseModel):
    """One scored option from the decision trace (SPEC section 7.4)."""

    model_config = ConfigDict(extra="forbid")

    skill: str
    score: float
    reason: str = ""
    chosen: bool = False


class MemoryDTO(BaseModel):
    """One remembered event."""

    model_config = ConfigDict(extra="forbid")

    tick: int
    type: str
    summary: str
    importance: int = 3


class LLMMindDTO(BaseModel):
    """What an LLM agent is thinking (SPEC section 9.4)."""

    model_config = ConfigDict(extra="forbid")

    thought: str = ""
    goal: str = ""
    plan: list[str] = Field(default_factory=list)
    say: str | None = None
    last_prompt: str | None = None
    last_response: str | None = None


class AgentDetailDTO(BaseModel):
    """`GET /api/agents/{id}` - everything the inspector shows."""

    model_config = ConfigDict(extra="forbid")

    summary: AgentSummaryDTO
    age: float
    life_stage: str
    needs: NeedsDTO
    traits: TraitsDTO
    inventory: dict[str, float] = Field(default_factory=dict)
    current_skill: str | None = None
    intent: str | None = None
    thought: str = ""
    decision_trace: list[DecisionOptionDTO] = Field(default_factory=list)
    relationships: list[RelationshipDTO] = Field(default_factory=list)
    memories: list[MemoryDTO] = Field(default_factory=list)
    llm: LLMMindDTO | None = None


class TribeDTO(BaseModel):
    """`GET /api/tribes` and `/api/tribes/{id}`."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    colour: str
    leader_id: int | None = None
    member_ids: list[int] = Field(default_factory=list)
    storage_food: float = 0.0
    camp_x: float = 0.0
    camp_z: float = 0.0
    territory_radius: float = 0.0
    at_war_with: list[int] = Field(default_factory=list)
    allied_with: list[int] = Field(default_factory=list)
