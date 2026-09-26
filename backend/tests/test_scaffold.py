from pathlib import Path

from sqlmodel import select

from contextos.config import Settings
from contextos.models import Document, Subject


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_watch_dirs_from_env(monkeypatch):
    monkeypatch.setenv("WATCH_DIRS", "~/Downloads, /tmp/notes")
    s = Settings(_env_file=None)
    assert s.watch_dirs == [Path.home() / "Downloads", Path("/tmp/notes")]


def test_tables_round_trip(session):
    session.add(Subject(name="Database Management Systems", aliases=["DBMS", "BCS403"]))
    session.add(Document(sha256="abc", original_path="/x.pdf", current_path="/x.pdf",
                         filename="x.pdf"))
    session.commit()
    subject = session.exec(select(Subject)).one()
    assert subject.aliases == ["DBMS", "BCS403"]
    assert session.exec(select(Document)).one().status == "new"
