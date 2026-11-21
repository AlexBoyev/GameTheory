"""Local Ollama provider (SPEC section 7.5).

Talks to `OLLAMA_URL/api/chat` with `format` set to the `Intention` JSON schema
and `think: false` where the model supports it. Never reaches the public
internet; failures fall back to `MockProvider`.
"""

import time

import httpx
import structlog

from app.ai.llm.provider import LLMError
from app.ai.llm.schemas import LLMRequest, LLMResponse

LOG = structlog.get_logger(__name__)

CHAT_PATH = "/api/chat"
TAGS_PATH = "/api/tags"


class OllamaProvider:
    """HTTP client for a locally running Ollama daemon."""

    name = "ollama"

    __slots__ = ("_client", "_model", "_send_think", "_timeout_s", "base_url")

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
        self._send_think = True
        """Whether to ask for thinking to be disabled.

        Only reasoning models accept `think`, and older daemons reject it
        outright. Rather than require the user to know which they have, the
        first rejection turns it off for the life of the provider (see
        `_is_think_rejection`).
        """

    @property
    def model(self) -> str:
        """Identifier of the model in use."""
        return self._model

    def _body(self, request: LLMRequest, *, think: bool) -> dict[str, object]:
        """The `/api/chat` payload for `request`."""
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        body: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        if request.json_schema is not None:
            # Constrained decoding: the daemon enforces the schema, which is
            # why malformed output is the exception and not the rule.
            body["format"] = request.json_schema
        if think:
            body["think"] = False
        return body

    @staticmethod
    def _is_think_rejection(response: httpx.Response) -> bool:
        """Whether this failure is the daemon objecting to `think`."""
        if response.status_code != httpx.codes.BAD_REQUEST:
            return False
        return "think" in response.text.lower()

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Run one chat completion against Ollama.

        Raises:
            LLMError: on timeout, transport failure, an error status, or a
                response with no content.
        """
        started = time.monotonic()
        try:
            reply = await self._client.post(
                CHAT_PATH, json=self._body(request, think=self._send_think)
            )
            if self._send_think and self._is_think_rejection(reply):
                LOG.info("llm.think_unsupported", model=self._model)
                self._send_think = False
                reply = await self._client.post(CHAT_PATH, json=self._body(request, think=False))
        except httpx.TimeoutException as error:
            msg = f"ollama timed out after {self._timeout_s}s"
            raise LLMError(msg) from error
        except httpx.HTTPError as error:
            msg = f"ollama unreachable: {error}"
            raise LLMError(msg) from error

        if reply.status_code != httpx.codes.OK:
            msg = f"ollama returned {reply.status_code}: {reply.text[:200]}"
            raise LLMError(msg)

        try:
            payload = reply.json()
        except ValueError as error:
            msg = "ollama returned a body that is not JSON"
            raise LLMError(msg) from error

        message = payload.get("message") or {}
        content = message.get("content") or ""
        if not isinstance(content, str) or not content.strip():
            msg = "ollama returned an empty message"
            raise LLMError(msg)

        return LLMResponse(
            agent_id=request.agent_id,
            kind=request.kind,
            content=content,
            model=str(payload.get("model") or self._model),
            provider=self.name,
            latency_s=round(time.monotonic() - started, 4),
            prompt_tokens_estimate=int(payload.get("prompt_eval_count") or 0),
        )

    async def healthy(self) -> bool:
        """Return True when the daemon answers `/api/tags`."""
        try:
            response = await self._client.get(TAGS_PATH, timeout=2.0)
        except httpx.HTTPError:
            return False
        return response.status_code == httpx.codes.OK

    async def models(self) -> tuple[str, ...]:
        """Names of the models the daemon has pulled, for the settings panel."""
        try:
            response = await self._client.get(TAGS_PATH, timeout=2.0)
            if response.status_code != httpx.codes.OK:
                return ()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return ()
        entries = payload.get("models") or []
        return tuple(str(entry.get("name", "")) for entry in entries if entry.get("name"))

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
