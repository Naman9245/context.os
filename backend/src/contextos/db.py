"""SQLite engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

from contextos import models  # noqa: F401 - registers the tables on SQLModel.metadata
from contextos.config import Settings, get_settings

_engine: Engine | None = None


def make_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:  # pragma: no cover - driver hook
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return engine


def get_engine(settings: Settings | None = None) -> Engine:
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        _engine = make_engine(settings.database_url)
    return _engine


def set_engine(engine: Engine | None) -> None:
    """Swap the engine - used by tests to point at a throwaway database."""
    global _engine
    _engine = engine


def init_db(engine: Engine | None = None) -> None:
    SQLModel.metadata.create_all(engine or get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with Session(get_engine()) as session:
        yield session
