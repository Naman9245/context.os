"""End to end through the HTTP API: scan -> review -> edit -> approve -> undo."""

from pathlib import Path

from sqlmodel import select

from contextos import llm
from contextos.models import Task, TaskStatus
from tests.makefiles import make_pdf


def _plan_by_name(client) -> dict[str, dict]:
    return {d["filename"]: d for d in client.get("/api/organize/plan").json()}


def test_full_organise_flow(client, settings, session):
    inbox: Path = settings.watch_dirs[0]
    client.post("/api/subjects", json={"name": "Database Management Systems",
                                       "code": "BCS403", "aliases": ["DBMS"], "semester": "4"})
    make_pdf(inbox / "DBMS_Assignment_2.pdf",
             "Assignment 2: Transactions\nLast date of submission: 28/12/2099")
    make_pdf(inbox / "dbms_module1_notes.pdf", "Module 1 Introduction to databases")
    make_pdf(inbox / "random.pdf", "nothing recognisable here at all")

    status = client.post("/api/organize/scan?wait=true").json()
    assert status["report"]["new"] == 3
    assert status["pending"] == 3

    plan = _plan_by_name(client)
    a = plan["DBMS_Assignment_2.pdf"]
    assert a["destination"] == "Sem 4/Database Management Systems/Assignments/DBMS Assignment 2.pdf"
    assert a["deadlines"][0]["status"] == "suggested"
    assert plan["random.pdf"]["destination"].startswith("General/Unsorted/")

    # Nothing has moved yet - the plan is a dry run.
    assert (inbox / "DBMS_Assignment_2.pdf").exists()
    assert not settings.library_root.exists()

    # Fix the unrecognised one by hand; a new subject gets created on the fly.
    edited = client.patch(f"/api/organize/documents/{plan['random.pdf']['id']}",
                          json={"subject": "Maths", "doc_type": "notes", "semester": "Sem 1"})
    assert edited.json()["destination"] == "Sem 1/Maths/Notes/Random.pdf"
    assert edited.json()["classified_by"] == "you"

    ids = [d["id"] for d in plan.values()]
    moved = client.post("/api/organize/apply", json={"document_ids": ids}).json()
    assert sorted(moved["moved"]) == sorted(ids)
    assert list(inbox.iterdir()) == []
    assert (settings.library_root / "Sem 1" / "Maths" / "Notes" / "Random.pdf").exists()

    files = client.get("/api/files").json()
    assert len(files) == 3
    assert client.get("/api/organize/status").json()["pending"] == 0

    # A rescan must not pick the organised files up again.
    assert client.post("/api/organize/scan?wait=true").json()["report"]["new"] == 0

    batch = client.get("/api/organize/batches").json()[0]
    assert batch["count"] == 3 and not batch["undone"]
    client.post(f"/api/organize/undo/{batch['batch_id']}")
    assert sorted(p.name for p in inbox.iterdir()) == sorted(
        ["DBMS_Assignment_2.pdf", "dbms_module1_notes.pdf", "random.pdf"])
    assert client.get("/api/organize/batches").json()[0]["undone"] is True

    tasks = session.exec(select(Task)).all()
    assert len(tasks) == 1 and tasks[0].status == TaskStatus.suggested


def test_duplicates_are_reported_not_imported(client, settings):
    inbox = settings.watch_dirs[0]
    make_pdf(inbox / "notes.pdf", "same content")
    (inbox / "notes (1).pdf").write_bytes((inbox / "notes.pdf").read_bytes())
    report = client.post("/api/organize/scan?wait=true").json()["report"]
    assert report["new"] == 1
    assert [Path(d["path"]).name for d in report["duplicates"]] == ["notes (1).pdf"]


def test_original_is_kept_when_its_own_name_has_a_number(client, settings):
    inbox = settings.watch_dirs[0]
    make_pdf(inbox / "Module3_final(2).pdf", "same content")
    (inbox / "Module3_final(2) (1).pdf").write_bytes((inbox / "Module3_final(2).pdf").read_bytes())
    report = client.post("/api/organize/scan?wait=true").json()["report"]
    assert [Path(d["path"]).name for d in report["duplicates"]] == ["Module3_final(2) (1).pdf"]


def test_subject_learns_its_semester_and_earlier_files_follow(client, settings):
    from tests.test_classify import FakeLLM

    replies = iter([
        {"doc_type": "lab", "subject": "Computer Networks", "title": "CN Lab Manual"},
        {"doc_type": "question_paper", "subject": "Computer Networks", "title": "CN Test 1",
         "semester": "Sem 5"},
    ])

    class Sequenced(FakeLLM):
        def complete_json(self, prompt, schema, *, system=""):
            self.reply = next(replies)
            return super().complete_json(prompt, schema, system=system)

    llm.set_llm(Sequenced({}))
    inbox = settings.watch_dirs[0]
    make_pdf(inbox / "a_unclear.pdf", "experiment one, simulate a network")  # no semester
    make_pdf(inbox / "b_unclear.pdf", "internal test, semester five")          # says Sem 5
    client.post("/api/organize/scan?wait=true")
    destinations = sorted(d["destination"] for d in client.get("/api/organize/plan").json())
    assert destinations == ["Sem 5/Computer Networks/Lab/CN Lab Manual.pdf",
                            "Sem 5/Computer Networks/Question Papers/CN Test 1.pdf"]


def test_skip_and_unskip(client, settings):
    make_pdf(settings.watch_dirs[0] / "keep_here.pdf", "x")
    client.post("/api/organize/scan?wait=true")
    doc_id = client.get("/api/organize/plan").json()[0]["id"]
    client.post("/api/organize/skip", json={"document_ids": [doc_id]})
    assert client.get("/api/organize/plan").json() == []
    assert len(client.get("/api/organize/plan?status=skipped").json()) == 1
    client.post("/api/organize/unskip", json={"document_ids": [doc_id]})
    assert len(client.get("/api/organize/plan").json()) == 1


def test_scan_uses_llm_for_unclear_files(client, settings):
    from tests.test_classify import FakeLLM

    fake = FakeLLM({"doc_type": "question_paper", "subject": "Physics", "title": "Physics 2024"})
    llm.set_llm(fake)
    make_pdf(settings.watch_dirs[0] / "scan0001.pdf", "some unclear text")
    report = client.post("/api/organize/scan?wait=true").json()["report"]
    assert report["used_llm"] == 1
    doc = client.get("/api/organize/plan").json()[0]
    assert doc["destination"] == "General/Physics/Question Papers/Physics 2024.pdf"
    assert doc["classified_by"] == "fake"


def test_subjects_crud(client):
    r = client.post("/api/subjects", json={"name": "OS", "aliases": [" Operating Systems ", ""]})
    assert r.status_code == 201 and r.json()["aliases"] == ["Operating Systems"]
    assert client.post("/api/subjects", json={"name": "os"}).status_code == 409
    sid = r.json()["id"]
    client.put(f"/api/subjects/{sid}", json={"name": "OS", "semester": "third"})
    assert client.get("/api/subjects").json()[0]["semester"] == "Sem 3"
    assert client.delete(f"/api/subjects/{sid}").status_code == 204
    assert client.get("/api/subjects").json() == []


def test_open_refuses_paths_outside_allowed_folders(client, session, tmp_path):
    from contextos.models import Document

    outside = make_pdf(tmp_path / "elsewhere" / "x.pdf", "x")
    doc = Document(sha256="z", original_path=str(outside), current_path=str(outside),
                   filename="x.pdf")
    session.add(doc)
    session.commit()
    assert client.post(f"/api/files/{doc.id}/open").status_code == 403


def test_requests_from_other_sites_are_refused(client):
    assert client.get("/api/health").status_code == 200
    evil_origin = client.post("/api/organize/scan", headers={"origin": "https://evil.example"})
    assert evil_origin.status_code == 403
    rebinding = client.get("/api/health", headers={"host": "evil.example"})
    assert rebinding.status_code == 403
    vite = client.get("/api/health", headers={"origin": "http://localhost:5173"})
    assert vite.status_code == 200
