"""The prompt payload that crosses from the simulation into `ai/llm/`.

`ai/llm/` must not import `app.sim` (import-linter: "ai/llm/ receives DTOs,
never sim internals"), and this is the DTO that makes that possible: plain
data, built by `ai.prompting` on the engine thread, rendered by the prompt
builder on the event loop.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PromptContext:
    """A render-ready snapshot of one agent's situation."""

    agent_id: int
    kind: str
    context: dict[str, Any] = field(default_factory=dict)
