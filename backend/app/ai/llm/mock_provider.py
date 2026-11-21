"""Deterministic offline provider - the default, and the fallback.

Builds a plausible `Intention` from a hash of the prompt, so the app is fully
usable (and tests are reproducible) with Ollama not installed.
"""

from zlib import crc32

from app.ai.llm.schemas import Intention, LLMRequest, LLMResponse, PlanStep

_GOALS: tuple[tuple[str, str, str], ...] = (
    ("stay fed", "Gather", "My stomach decides my politics today."),
    ("make an ally", "Talk", "A friend is cheaper than a fight."),
    ("win the island", "Gossip", "Words travel further than fists."),
    ("keep what is mine", "Flee", "Better cautious than dead."),
    ("lead them", "FoundTribe", "Someone has to decide, so it may as well be me."),
)


class MockProvider:
    """Heuristic provider with no network access."""

    name = "mock"

    def __init__(self, model: str = "mock-deterministic") -> None:
        self._model = model
        self.calls = 0

    @property
    def model(self) -> str:
        """Identifier of the model in use."""
        return self._model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Return a deterministic intention derived from the request."""
        self.calls += 1
        seed = crc32(f"{request.agent_id}:{request.cache_key or request.prompt}".encode())
        goal, skill, thought = _GOALS[seed % len(_GOALS)]
        intention = Intention(
            thought=thought,
            goal=goal,
            plan=[PlanStep(skill=skill, params={})],
            say=None if seed % 3 else thought,
        )
        return LLMResponse(
            agent_id=request.agent_id,
            kind=request.kind,
            content=intention.model_dump_json(),
            model=self._model,
            provider=self.name,
            prompt_tokens_estimate=len(request.prompt) // 4,
        )

    async def healthy(self) -> bool:
        """Always reachable - it is in-process."""
        return True

    async def aclose(self) -> None:
        """Nothing to release."""
        return None
