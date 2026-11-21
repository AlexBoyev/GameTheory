"""Local Ollama provider (SPEC section 7.5). Implemented in Phase 5.

Talks to `OLLAMA_URL/api/chat` with `format` set to the `Intention` JSON schema
and `think: false` where the model supports it. Never reaches the public
internet; failures fall back to `MockProvider`.
"""

import httpx

from app.ai.llm.schemas import LLMRequest, LLMResponse

CHAT_PATH = "/api/chat"
TAGS_PATH = "/api/tags"


class OllamaProvider:
    """HTTP client for a locally running Ollama daemon."""

    name = "ollama"

    __slots__ = ("_client", "_model", "_timeout_s", "base_url")

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        timeout_s: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s)

    @property
    def model(self) -> str:
        """Identifier of the model in use."""
        return self._model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Run one chat completion against Ollama."""
        msg = "OllamaProvider.generate() arrives in Phase 5 (LLM minds)"
        raise NotImplementedError(msg)

    async def healthy(self) -> bool:
        """Return True when the daemon answers `/api/tags`."""
        try:
            response = await self._client.get(TAGS_PATH, timeout=2.0)
        except httpx.HTTPError:
            return False
        return response.status_code == httpx.codes.OK

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
