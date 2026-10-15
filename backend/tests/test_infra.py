import threading

from sqlalchemy import inspect, text

from contextos import db
from contextos.ingest.watcher import FolderWatcher


def test_init_db_adds_columns_new_phases_introduce(tmp_path):
    """A Phase 0 database gains Phase 2's columns without losing its rows."""
    engine = db.make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE document (id INTEGER PRIMARY KEY, sha256 VARCHAR NOT NULL, "
            "original_path VARCHAR NOT NULL, current_path VARCHAR NOT NULL, "
            "filename VARCHAR NOT NULL, doc_type VARCHAR, status VARCHAR, confidence FLOAT, "
            "text_snippet VARCHAR, created_at DATETIME, updated_at DATETIME)"))
        conn.execute(text("INSERT INTO document (sha256, original_path, current_path, filename) "
                          "VALUES ('h', '/a.pdf', '/a.pdf', 'a.pdf')"))

    db.init_db(engine)

    columns = {c["name"] for c in inspect(engine).get_columns("document")}
    assert {"extraction", "classified_by", "size_bytes", "mtime", "error"} <= columns
    with engine.connect() as conn:
        assert conn.execute(text("SELECT size_bytes FROM document")).scalar() == 0
    engine.dispose()


def test_watcher_debounces_a_burst_into_one_scan(tmp_path):
    calls = []
    fired = threading.Event()

    def on_change():
        calls.append(1)
        fired.set()

    w = FolderWatcher([tmp_path], on_change, debounce_seconds=0.05)
    for _ in range(5):
        w._poke(str(tmp_path / "notes.pdf"))
    w._poke(str(tmp_path / "notes.pdf.crdownload"))  # ignored: still downloading
    assert fired.wait(2)
    assert calls == [1]
