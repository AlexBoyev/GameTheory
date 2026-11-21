"""A tiny `Result` type used by skill preconditions (SPEC section 7.3).

Skills return `Ok(None)` or `Err("reason")` so the reason can be shown in the
inspector and fed back to an LLM that proposed an invalid plan.
"""

from dataclasses import dataclass
from typing import TypeGuard


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """A successful result carrying a value."""

    value: T


@dataclass(frozen=True, slots=True)
class Err[E]:
    """A failed result carrying a reason."""

    error: E


type Result[T, E] = Ok[T] | Err[E]
"""Either `Ok(value)` or `Err(error)`."""

OK_NONE: Ok[None] = Ok(None)
"""Shared "precondition satisfied" singleton."""


def is_ok[T, E](result: Result[T, E]) -> TypeGuard[Ok[T]]:
    """Narrow `result` to `Ok` for type checkers."""
    return isinstance(result, Ok)
