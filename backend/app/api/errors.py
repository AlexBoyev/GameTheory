"""Shared HTTP failures, including the honest "not built yet" response."""

from fastapi import HTTPException, status


def not_implemented_yet(what: str, phase: int) -> HTTPException:
    """Return a 501 that names the phase an endpoint is scheduled for.

    Better than a plausible-looking empty payload: the frontend can show a
    "coming in phase N" placeholder instead of silently rendering nothing.
    """
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{what} is implemented in Phase {phase}",
    )


def not_found(what: str) -> HTTPException:
    """Return a 404 for a missing entity."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def bad_request(detail: str) -> HTTPException:
    """Return a 400 with `detail`."""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
