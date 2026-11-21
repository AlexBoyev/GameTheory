"""The LLM gateway - local models only.

Hard rule (CLAUDE.md): no cloud providers, no API keys, no billing. Only
`OllamaProvider` (localhost) and the deterministic `MockProvider`, which is
also the automatic fallback whenever Ollama is unreachable.

The simulation never awaits an LLM call: requests are queued, and results are
applied as intention bias when (and if) they arrive.
"""

from app.ai.llm.gateway import LLMGateway, LLMStatus
from app.ai.llm.provider import LLMError, LLMProvider
from app.ai.llm.schemas import Intention, LLMRequest, LLMResponse, PlanStep, Reflection

__all__ = [
    "Intention",
    "LLMError",
    "LLMGateway",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMStatus",
    "PlanStep",
    "Reflection",
]
