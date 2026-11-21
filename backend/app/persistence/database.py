"""Engine and session plumbing for SQLite."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.settings import Settings


def build_engine(settings: Settings) -> Engine:
    """Create the SQLite engine, making `data_dir` if needed.

    `check_same_thread=False` is required because the engine thread and the
    asyncio thread both touch the database.
    """
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    return create_engine(
        settings.database_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )


def create_tables(engine: Engine) -> None:
    """Create any missing tables (no migrations - this is a sandbox)."""
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Yield a session, committing on success and rolling back on error."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
