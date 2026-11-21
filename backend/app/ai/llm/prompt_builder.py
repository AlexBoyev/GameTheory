"""Jinja2 prompt assembly (SPEC section 7.5). Templates live in `prompts/`.

Target budget is under 1,500 tokens per prompt; the builder logs an estimate so
regressions are visible in the LLM monitor.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

PROMPTS_DIR = Path(__file__).parent / "prompts"
TOKEN_BUDGET = 1500
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token count - good enough for budget alarms, not for billing."""
    return len(text) // CHARS_PER_TOKEN


class PromptBuilder:
    """Renders the persona/situation/memory/skills prompt for an agent."""

    __slots__ = ("_env",)

    def __init__(self, templates_dir: Path | None = None) -> None:
        self._env = Environment(
            loader=FileSystemLoader(templates_dir or PROMPTS_DIR),
            autoescape=select_autoescape(enabled_extensions=(), default=False),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    @property
    def templates(self) -> list[str]:
        """Available template names."""
        return sorted(self._env.list_templates())

    def render(self, template: str, /, **context: object) -> str:
        """Render `template` with `context`."""
        return self._env.get_template(template).render(**context)

    def build_intention_prompt(self, context: dict[str, Any]) -> str:
        """Build the deliberation prompt from an agent's situation.

        `context` is a plain snapshot taken on the engine thread (see
        `ai.llm.snapshot`), never live entities: by the time this renders, the
        world has moved on.
        """
        return self.render("intention.j2", **context).strip()

    def build_reflection_prompt(self, context: dict[str, Any]) -> str:
        """Build the prompt that turns recent events into durable beliefs."""
        return self.render("reflection.j2", **context).strip()

    def over_budget(self, prompt: str) -> bool:
        """Whether `prompt` exceeds the token budget worth warning about."""
        return estimate_tokens(prompt) > TOKEN_BUDGET
