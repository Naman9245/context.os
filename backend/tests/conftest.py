import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from contextos import db
from contextos.main import create_app


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
    with TestClient(create_app()) as c:
        yield c
