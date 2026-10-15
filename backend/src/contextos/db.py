"""SQLite engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, event, inspect, text
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
    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine: Engine) -> None:
    """create_all never alters an existing table, so add columns new phases introduce.

    Only additive changes are handled - enough for a single-user local app
    whose schema grows phase by phase. New columns must be nullable or have a
    default.
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl_type = column.type.compile(dialect=engine.dialect)
                default = column.default.arg if column.default is not None else None
                clause = ""
                if isinstance(default, bool):
                    clause = f" DEFAULT {int(default)}"
                elif isinstance(default, int | float):
                    clause = f" DEFAULT {default}"
                elif isinstance(default, str):
                    clause = " DEFAULT '{}'".format(default.replace("'", "''"))
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}{clause}'
                conn.execute(text(ddl))


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with Session(get_engine()) as session:
        yield session
