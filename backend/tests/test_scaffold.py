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


def test_build_id_changes_when_the_frontend_is_rebuilt(client, tmp_path, monkeypatch):
    from contextos import frontend

    dist = tmp_path / "dist"
    dist.mkdir()
    monkeypatch.setattr(frontend, "FRONTEND_DIST", dist)
    assert client.get("/api/health").json()["build"] is None
    (dist / "index.html").write_text('<script src="/assets/index-AAA.js"></script>')
    first = client.get("/api/health").json()["build"]
    (dist / "index.html").write_text('<script src="/assets/index-BBB.js"></script>')
    assert first and client.get("/api/health").json()["build"] != first


def test_index_html_is_never_served_stale(engine, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from contextos import frontend
    from contextos.main import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    monkeypatch.setattr(frontend, "FRONTEND_DIST", dist)
    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as c:
        r = c.get("/chat")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
