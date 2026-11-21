"""The provider seam. Implementations: `MockProvider`, `OllamaProvider`."""

from typing import Protocol, runtime_checkable

from app.ai.llm.schemas import LLMRequest, LLMResponse


class LLMError(RuntimeError):
    """Raised when a provider call fails (timeout, HTTP error, bad JSON)."""


@runtime_checkable
class LLMProvider(Protocol):
    """Turns an `LLMRequest` into an `LLMResponse`.

    Implementations must be cancellable and must never block the event loop.
    """

    name: str

    @property
    def model(self) -> str:
        """Identifier of the model in use."""
        ...

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Run one completion.

        Raises:
            LLMError: on timeout, transport failure or unusable output.
        """
        ...

    async def healthy(self) -> bool:
        """Return whether the backing service is reachable right now."""
        ...

    async def aclose(self) -> None:
        """Release transport resources."""
        ...
