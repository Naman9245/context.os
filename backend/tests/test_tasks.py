"""Assignments, Khushi's questions, to-do steps, reminders and the briefing."""

from datetime import date, datetime, timedelta

import pytest
from sqlmodel import select

from contextos import llm
from contextos.agent.khushi import build_briefing
from contextos.models import (
    ActivityEvent,
    DocStatus,
    DocType,
    Document,
    Task,
    TaskSource,
    TaskStatus,
    TaskStep,
)
from contextos.tasks.reminders import pending_offsets, reminder_text, run_reminders
from contextos.tasks.service import due_from_date, ensure_assignment_tasks
from contextos.tasks.steps import generate_steps, rule_steps
from tests.makefiles import make_pdf
from tests.test_classify import FakeLLM

TODAY = date(2026, 10, 15)
NOW = datetime(2026, 10, 15, 9, 0)


def _task(session, title="DBMS Assignment 2", days=5, status=TaskStatus.todo, **kw) -> Task:
    t = Task(title=title, status=status,
             due_at=due_from_date(TODAY + timedelta(days=days)) if days is not None else None,
             **kw)
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


# -- scanning creates the right tasks ----------------------------------------------


def test_assignment_without_deadline_becomes_a_question(client, settings, session):
    inbox = settings.watch_dirs[0]
    make_pdf(inbox / "DAA_Assignment_3.pdf", "Assignment 3\nQ1. Prove the master theorem.")
    make_pdf(inbox / "DBMS_Assignment_2.pdf", "Assignment 2\nLast date of submission: 28/12/2099")
    make_pdf(inbox / "dbms_notes.pdf", "Module 1 notes")  # not an assignment: no task
    client.post("/api/organize/scan?wait=true")

    tasks = {t["title"]: t for t in client.get("/api/tasks").json()}
    assert set(tasks) == {"DAA Assignment 3", "DBMS Assignment 2"}
    assert tasks["DAA Assignment 3"]["status"] == "suggested"
    assert tasks["DAA Assignment 3"]["due_at"] is None
    assert tasks["DBMS Assignment 2"]["due_at"].startswith("2099-12-28")

    # Rescanning must not ask the same question twice.
    client.post("/api/organize/scan?wait=true")
    assert len(client.get("/api/tasks").json()) == 2


def test_backfill_for_assignments_scanned_before_tasks_existed(session):
    doc = Document(sha256="x", original_path="/a.pdf", current_path="/a.pdf", filename="a.pdf",
                   doc_type=DocType.assignment, title="OS Assignment 1",
                   status=DocStatus.organized)
    session.add(doc)
    session.commit()
    assert ensure_assignment_tasks(session) == 1
    assert ensure_assignment_tasks(session) == 0  # idempotent
    task = session.exec(select(Task)).one()
    assert (task.title, task.status, task.due_at) == ("OS Assignment 1", "suggested", None)


def test_relabelling_a_file_adds_or_drops_its_question(client, settings):
    make_pdf(settings.watch_dirs[0] / "week3.pdf", "Module 3 notes on scheduling")
    client.post("/api/organize/scan?wait=true")
    doc_id = client.get("/api/organize/plan").json()[0]["id"]
    assert client.get("/api/tasks").json() == []

    client.patch(f"/api/organize/documents/{doc_id}", json={"doc_type": "assignment"})
    assert [t["status"] for t in client.get("/api/tasks").json()] == ["suggested"]

    client.patch(f"/api/organize/documents/{doc_id}", json={"doc_type": "notes"})
    assert client.get("/api/tasks").json() == []


# -- answering Khushi ------------------------------------------------------------------


def test_giving_a_deadline_accepts_the_task(client, session):
    t = _task(session, days=None, status=TaskStatus.suggested, source=TaskSource.extracted)
    r = client.patch(f"/api/tasks/{t.id}", json={"due_date": "2099-11-02"}).json()
    assert r["status"] == "todo" and r["due_at"] == "2099-11-02T23:59:00"


def test_no_deadline_answer_keeps_it_undated(client, session):
    t = _task(session, days=None, status=TaskStatus.suggested, source=TaskSource.extracted)
    r = client.patch(f"/api/tasks/{t.id}", json={"status": "todo"}).json()
    assert r["status"] == "todo" and r["due_at"] is None


def test_dismissed_deadline_is_not_suggested_again(client, settings):
    make_pdf(settings.watch_dirs[0] / "Lab_Assignment.pdf", "Assignment\nDue date: 01/01/2099")
    client.post("/api/organize/scan?wait=true")
    task_id = client.get("/api/tasks").json()[0]["id"]
    assert client.delete(f"/api/tasks/{task_id}").status_code == 204
    assert client.get("/api/tasks").json() == []
    client.post("/api/organize/scan?wait=true")
    assert client.get("/api/tasks").json() == []


def test_manual_task_lifecycle(client, session):
    r = client.post("/api/tasks", json={"title": "Physics lab record", "subject": "Physics",
                                        "due_date": "2099-01-10"})
    assert r.status_code == 201
    t = r.json()
    assert (t["status"], t["subject"], t["source"]) == ("todo", "Physics", "manual")

    done = client.patch(f"/api/tasks/{t['id']}", json={"status": "done"}).json()
    assert done["status"] == "done" and done["completed_at"]
    assert len(session.exec(select(ActivityEvent)).all()) == 1

    # Un-ticking removes it from this week's "finished" count.
    client.patch(f"/api/tasks/{t['id']}", json={"status": "todo"})
    session.expire_all()
    assert session.exec(select(ActivityEvent)).all() == []

    assert client.delete(f"/api/tasks/{t['id']}").status_code == 204
    assert client.get("/api/tasks").json() == []


def test_tasks_are_listed_soonest_first_with_undated_last(client, session):
    _task(session, "later", days=20)
    _task(session, "undated", days=None)
    _task(session, "soon", days=2)
    assert [t["title"] for t in client.get("/api/tasks").json()] == ["soon", "later", "undated"]


def test_changing_the_date_resets_reminders(client, session):
    t = _task(session, days=4)
    t.reminded_days = [5]
    session.add(t)
    session.commit()
    client.patch(f"/api/tasks/{t.id}", json={"due_date": "2099-05-05"})
    session.expire_all()
    assert session.get(Task, t.id).reminded_days == []


# -- to-do steps ------------------------------------------------------------------------


def test_rule_steps_use_the_real_questions():
    text = ("Assignment 2\nQ1. Explain ACID properties with examples.\n"
            "Q2: Draw the precedence graph for schedule S.\n3) Define serializability.")
    steps = rule_steps(text, "DBMS Assignment 2", "DBMS")
    assert steps == [
        "Answer Q1: Explain ACID properties with examples",
        "Answer Q2: Draw the precedence graph for schedule S",
        "Answer Q3: Define serializability",
        "Review your answers and submit",
    ]


def test_rule_steps_without_questions_are_still_useful():
    steps = rule_steps("Write a report on TCP.", "CN Report", "Computer Networks")
    assert steps[1] == "Collect what you need from your Computer Networks notes"
    assert steps[-1] == "Review your answers and submit"


def test_ai_steps_and_fallback():
    fake = FakeLLM({"steps": ["Read chapter 4", "Solve Q1", "Submit on Moodle"]})
    steps, by, err = generate_steps(title="T", subject=None, due_at=None, text="Q1. x",
                                    llm=fake)
    assert (steps, by, err) == (["Read chapter 4", "Solve Q1", "Submit on Moodle"], "fake", None)

    from contextos.llm import LLMError
    steps, by, err = generate_steps(title="T", subject=None, due_at=None,
                                    text="Q1. Explain paging", llm=FakeLLM(LLMError("quota")))
    assert by == "rules" and "quota" in err and steps[0] == "Answer Q1: Explain paging"


def test_generate_tick_add_and_delete_steps(client, settings):
    make_pdf(settings.watch_dirs[0] / "OS_Assignment_1.pdf",
             "OS Assignment 1\nQ1. Explain paging.\nQ2. Compare FCFS and SJF.")
    client.post("/api/organize/scan?wait=true")
    task_id = client.get("/api/tasks").json()[0]["id"]

    t = client.post(f"/api/tasks/{task_id}/steps/generate").json()
    assert [s["text"] for s in t["steps"]][:2] == ["Answer Q1: Explain paging",
                                                    "Answer Q2: Compare FCFS and SJF"]
    assert client.post(f"/api/tasks/{task_id}/steps/generate").status_code == 409

    first = t["steps"][0]["id"]
    t = client.patch(f"/api/tasks/steps/{first}", json={"done": True}).json()
    assert t["steps"][0]["done"] is True

    t = client.post(f"/api/tasks/{task_id}/steps", json={"text": "Ask Priya for notes"}).json()
    assert t["steps"][-1] == {"id": t["steps"][-1]["id"], "text": "Ask Priya for notes",
                              "done": False, "written_by": "you"}
    t = client.delete(f"/api/tasks/steps/{first}").json()
    assert first not in [s["id"] for s in t["steps"]]


def test_ai_writes_steps_when_configured(client, settings):
    make_pdf(settings.watch_dirs[0] / "DBMS_Assignment_9.pdf", "Assignment 9\nQ1. Normalise R.")
    client.post("/api/organize/scan?wait=true")
    llm.set_llm(FakeLLM({"steps": ["Revise normal forms", "Do Q1", "Submit"]}))
    task_id = client.get("/api/tasks").json()[0]["id"]
    t = client.post(f"/api/tasks/{task_id}/steps/generate").json()
    assert [s["written_by"] for s in t["steps"]] == ["fake"] * 3


# -- reminders ------------------------------------------------------------------------


@pytest.mark.parametrize("days_left, already, expected", [
    (6, [], []),          # too early
    (5, [], [5]),         # five days before
    (3, [5], [3]),        # three days before
    (2, [], [5, 3]),      # laptop was off: one catch-up covers both
    (2, [5, 3], []),      # nothing new
    (-1, [], []),         # overdue: no reminder
])
def test_pending_offsets(session, days_left, already, expected):
    t = _task(session, days=days_left)
    t.reminded_days = already
    assert pending_offsets(t, TODAY, [5, 3]) == expected


def test_only_accepted_tasks_are_reminded(session):
    for status in (TaskStatus.suggested, TaskStatus.done, TaskStatus.dismissed):
        assert pending_offsets(_task(session, days=3, status=status), TODAY, [5, 3]) == []


def test_run_reminders_sends_each_once(session):
    t = _task(session, days=5)
    session.add(TaskStep(task_id=t.id, text="a", done=True))
    session.add(TaskStep(task_id=t.id, text="b"))
    session.commit()
    sent = []

    def send(title, body):
        sent.append((title, body))
        return True

    run_reminders(session, now=NOW, offsets=[5, 3], send=send)
    run_reminders(session, now=NOW, offsets=[5, 3], send=send)
    assert len(sent) == 1
    assert sent[0][0] == "DBMS Assignment 2 is due in 5 days"
    assert "1 of 2 steps" in sent[0][1]


def test_failed_notification_is_retried_next_time(session):
    _task(session, days=3)
    assert run_reminders(session, now=NOW, offsets=[5, 3], send=lambda t, b: False) == []
    assert len(run_reminders(session, now=NOW, offsets=[5, 3], send=lambda t, b: True)) == 1


def test_reminder_wording(session):
    t = _task(session, days=1)
    title, body = reminder_text(t, TODAY, "DBMS", 0, 4)
    assert title == "DBMS Assignment 2 is due tomorrow"
    assert body.startswith("DBMS. Due Friday 16 October 2026.")
    assert "start with the first one" in body


# -- Khushi's briefing ------------------------------------------------------------------


def test_briefing_mentions_what_matters(session):
    _task(session, "DBMS Assignment 2", days=3)
    _task(session, "OS Lab", days=-1)
    _task(session, "DAA Assignment II", days=None, status=TaskStatus.suggested,
          source=TaskSource.extracted)
    _task(session, "Fee payment", days=9, status=TaskStatus.suggested,
          source=TaskSource.extracted)
    b = build_briefing(session, NOW)
    text = " ".join(line.text for line in b.lines)
    assert b.greeting == "Good morning! I'm Khushi."
    assert "OS Lab is overdue" in text
    assert "Due this week: DBMS Assignment 2 (Sun 18 Oct 2026)" in text
    assert "I couldn't find a deadline in DAA Assignment II. When is it due?" in text
    assert "I spotted 1 deadline in your files" in text


def test_briefing_when_all_caught_up(session):
    b = build_briefing(session, datetime(2026, 10, 15, 20, 0))
    assert b.greeting == "Good evening! I'm Khushi."
    assert [line.text for line in b.lines] == ["You're all caught up. Nice work!"]


def test_briefing_endpoint(client):
    r = client.get("/api/khushi/briefing").json()
    assert r["name"] == "Khushi" and r["lines"]


def test_test_notification_endpoint(client, monkeypatch):
    from contextos.api import tasks as tasks_api

    shown = []
    monkeypatch.setattr(tasks_api, "notify", lambda t, b: shown.append(t) or True)
    assert client.post("/api/tasks/test-notification").json()["sent"] is True
    assert shown == ["Hi, I'm Khushi!"]


def test_reminder_days_from_env(monkeypatch):
    from contextos.config import Settings

    monkeypatch.setenv("REMINDER_DAYS", "1, 5,3")
    assert Settings(_env_file=None).reminder_days == [5, 3, 1]
