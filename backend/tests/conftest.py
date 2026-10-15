import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from contextos import db, llm
from contextos.config import Settings, set_settings
from contextos.main import create_app


@pytest.fixture(autouse=True)
def settings(tmp_path):
    """Every test gets throwaway folders and heuristics-only mode.

    `_env_file=None` matters: backend/.env holds the developer's real API key
    and real folders, and no test may read either.
    """
    s = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        library_root=tmp_path / "library",
        watch_dirs=[tmp_path / "inbox"],
        watch_enabled=False,
        llm_provider="none",
    )
    (tmp_path / "inbox").mkdir()
    set_settings(s)
    llm.set_llm(None)
    yield s
    set_settings(None)
    llm.set_llm(None)


@pytest.fixture
def engine(tmp_path):
    engine = db.make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    db.set_engine(engine)
    db.init_db(engine)
    yield engine
    db.set_engine(None)
    engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine):
    # base_url matters: the API rejects requests whose Host is not localhost.
    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as c:
        yield c
