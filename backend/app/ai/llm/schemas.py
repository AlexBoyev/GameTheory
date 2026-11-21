"""Structured LLM input and output (SPEC section 7.5).

`Intention` is the contract the model must satisfy; its JSON schema is sent to
Ollama as `format`, so well-formed output is the normal case and the repair
retry is the exception.
"""

from pydantic import BaseModel, ConfigDict, Field


class PlanStep(BaseModel):
    """One skill call in a plan."""

    model_config = ConfigDict(extra="forbid")

    skill: str = Field(description="Name of a registered skill.")
    params: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        description="Parameters matching that skill's schema.",
    )


class Intention(BaseModel):
    """What an LLM agent decided to try next.

    Biases utility scores until it is done, expired or invalid - survival urges
    can still override it (a starving schemer eats first).
    """

    model_config = ConfigDict(extra="forbid")

    thought: str = Field(description="Private reasoning, 1-2 sentences.", max_length=400)
    goal: str = Field(description="Short goal statement.", max_length=120)
    plan: list[PlanStep] = Field(default_factory=list, max_length=3)
    say: str | None = Field(default=None, description="Public line, or null.", max_length=160)

    @property
    def skills(self) -> tuple[str, ...]:
        """Skill names referenced by the plan, in order."""
        return tuple(step.skill for step in self.plan)


class Reflection(BaseModel):
    """A summary the agent writes about itself every N important events."""

    model_config = ConfigDict(extra="forbid")

    beliefs: list[str] = Field(default_factory=list, max_length=5)
    summary: str = Field(default="", max_length=400)


class LLMRequest(BaseModel):
    """One queued call. `cache_key` is the prompt hash used by the LRU cache."""

    model_config = ConfigDict(extra="forbid")

    agent_id: int
    kind: str = Field(default="intention", description="intention | reflection")
    system: str = ""
    prompt: str = ""
    json_schema: dict[str, object] | None = None
    max_tokens: int = 512
    temperature: float = 0.7
    issued_sim_s: float = 0.0
    cache_key: str = ""


class LLMResponse(BaseModel):
    """A completed call, successful or not."""

    model_config = ConfigDict(extra="forbid")

    agent_id: int
    kind: str = "intention"
    content: str = ""
    model: str = ""
    provider: str = ""
    latency_s: float = 0.0
    cached: bool = False
    prompt_tokens_estimate: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when the call produced usable content."""
        return self.error is None and bool(self.content)
