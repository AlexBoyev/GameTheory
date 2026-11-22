"""Shared HTTP failures."""

from fastapi import HTTPException, status


def not_found(what: str) -> HTTPException:
    """Return a 404 for a missing entity."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def bad_request(detail: str) -> HTTPException:
    """Return a 400 with `detail`."""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
