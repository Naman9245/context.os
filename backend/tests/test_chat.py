"""Khushi's chat: rules, actions, the LLM fallback, and history."""

from datetime import date, timedelta

import pytest
from sqlmodel import select

from contextos import llm
from contextos.agent import actions, tools
from contextos.agent.intents import parse
from contextos.models import DocStatus, DocType, Document, Subject, Task, TaskStatus
from contextos.tasks.deadlines import parse_when
from contextos.tasks.service import due_from_date
from tests.test_classify import FakeLLM


@pytest.fixture
def opened(monkeypatch):
    """Record what Khushi would launch or open instead of really doing it."""
    log: list[tuple[str, str]] = []
    monkeypatch.setattr(actions, "_spawn", lambda argv: log.append(("spawn", " ".join(argv))))
    monkeypatch.setattr(actions, "_open_with_system", lambda t: log.append(("open", t)))
    return log


@pytest.fixture
def installed(monkeypatch):
    """Pretend exactly these apps are installed."""
    apps: set[str] = set()

    def fake(app):
        return f"/usr/bin/{app.key}" if app.key in apps else None

    monkeypatch.setattr(actions, "installed_command", fake)
    monkeypatch.setattr(tools, "installed_command", fake)
    return apps


def say(client, text: str) -> dict:
    r = client.post("/api/chat", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()["reply"]


# -- understanding ------------------------------------------------------------------


@pytest.mark.parametrize("text, name, args", [
    ("Hey Khushi, can you open Spotify for me please?", "open", {"target": "Spotify"}),
    ("Open Google Chrome", "open", {"target": "Google Chrome"}),
    ("play lofi on youtube", "play", {"q": "lofi", "where": "youtube"}),
    ("play arijit singh on spotify", "play", {"q": "arijit singh", "where": "spotify"}),
    ("search black holes on wikipedia", "search", {"q": "black holes", "where": "wikipedia"}),
    ("search wikipedia for alan turing", "search", {"where": "wikipedia", "q": "alan turing"}),
    ("search games on Google in Google Chrome", "search", {"q": "games", "where": "Google"}),
    ("google how to make tea", "search", {"where": "google", "q": "how to make tea"}),
    ("what's due this week?", "list_tasks", {"when": "this week"}),
    ("my assignments", "list_tasks", {}),
    ("I finished the DBMS assignment", "complete_task", {"q": "DBMS assignment"}),
    ("mark OS lab record as done", "complete_task", {"q": "OS lab record"}),
    ("add DBMS mini project due friday", "add_task", {"q": "DBMS mini project due friday"}),
    ("remind me to pay the exam fee on monday", "add_task", {"q": "pay the exam fee on monday"}),
    ("organise my files", "organize", {}),
    ("find my DBMS notes", "find_files", {"q": "DBMS notes"}),
    ("what time is it", "time", {}),
])
def test_rules_understand_everyday_commands(text, name, args):
    intent = parse(text)
    assert intent is not None and (intent.name, intent.args) == (name, args)


def test_greeting_keeps_working_with_her_name():
    assert parse("hi khushi").name == "greet"
    assert parse("Hey Khushi, open spotify").args == {"target": "spotify"}


@pytest.mark.parametrize("text", ["what is a deadlock", "explain paging to me",
                                  "I'm stressed about exams"])
def test_open_ended_questions_are_left_for_the_llm(text):
    assert parse(text) is None


@pytest.mark.parametrize("text, days, rest", [
    ("DBMS assignment due Friday", 1, "DBMS assignment"),       # 2026-10-15 is a Thursday
    ("submit OS lab record by tomorrow", 1, "submit OS lab record"),
    ("physics report in 3 days", 3, "physics report"),
    ("fee payment this sunday", 3, "fee payment"),
    ("CN project due 25 oct", 10, "CN project"),
    ("read chapter 4", None, "read chapter 4"),
])
def test_parse_when(text, days, rest):
    today = date(2026, 10, 15)
    due, left = parse_when(text, today)
    assert left == rest
    assert due == (today + timedelta(days=days) if days is not None else None)


# -- apps, websites, search -----------------------------------------------------------


def test_open_installed_app(client, opened, installed):
    installed.add("spotify")
    reply = say(client, "open spotify")
    assert reply["text"] == "Opening Spotify!"
    assert opened == [("spawn", "/usr/bin/spotify")]


def test_missing_app_falls_back_to_the_web(client, opened, installed):
    reply = say(client, "open discord")
    assert "isn't installed" in reply["text"]
    assert opened == [("open", "https://discord.com/app")]


def test_open_website(client, opened):
    assert say(client, "open youtube")["text"] == "Opening Youtube."
    assert opened == [("open", "https://www.youtube.com")]


def test_play_on_youtube_and_spotify(client, opened, installed):
    say(client, "play lofi beats on youtube")
    installed.add("spotify")
    say(client, "play arijit singh on spotify")
    assert opened == [
        ("open", "https://www.youtube.com/results?search_query=lofi+beats"),
        ("open", "spotify:search:arijit%20singh"),
    ]


def test_search_engines(client, opened):
    say(client, "search black holes on wikipedia")
    say(client, "search games in google chrome")
    assert opened == [
        ("open", "https://en.wikipedia.org/wiki/Special:Search?search=black+holes"),
        ("open", "https://www.google.com/search?q=games"),
    ]


def test_only_web_links_can_be_opened(opened):
    for url in ("file:///etc/passwd", "javascript:alert(1)", "ssh://x"):
        with pytest.raises(actions.ActionNotAllowed):
            actions.open_url(url)
    assert opened == []


# -- assignments ------------------------------------------------------------------------


def _add(session, title, days, subject=None):
    t = Task(title=title, status=TaskStatus.todo, subject_id=subject,
             due_at=due_from_date(date.today() + timedelta(days=days)))
    session.add(t)
    session.commit()
    return t


def test_whats_due_this_week(client, session):
    _add(session, "DBMS Assignment 2", 3)
    _add(session, "DAA Assignment II", 20)
    reply = say(client, "what's due this week?")
    assert reply["text"] == "You have 1 thing due this week:"
    assert [t["title"] for t in reply["tasks"]] == ["DBMS Assignment 2"]


def test_nothing_due(client):
    assert say(client, "what's due today")["text"] == "Nothing due today. Nice!"


def test_add_task_by_chat(client, session):
    session.add(Subject(name="Database Management Systems", aliases=["DBMS"]))
    session.commit()
    reply = say(client, "add DBMS mini project due tomorrow")
    task = reply["tasks"][0]
    assert task["title"] == "DBMS mini project"
    assert task["subject"] == "Database Management Systems"
    assert task["due_at"][:10] == (date.today() + timedelta(days=1)).isoformat()
    assert "I'll remind you 5 and 3 days before" in reply["text"]
    from contextos.tasks.service import long_date

    assert f"due {long_date(date.today() + timedelta(days=1))}." in reply["text"]


def test_finish_assignment_by_chat(client, session):
    dbms = Subject(name="Database Management Systems", aliases=["DBMS"])
    session.add(dbms)
    session.commit()
    t = _add(session, "Assignment 2", 3, subject=dbms.id)
    reply = say(client, "I finished the DBMS assignment")
    assert reply["text"] == "Nice work! I've marked “Assignment 2” as finished."
    session.refresh(t)
    assert t.status == TaskStatus.done


def test_ambiguous_finish_asks_which(client, session):
    _add(session, "DBMS Assignment 1", 3)
    _add(session, "DBMS Assignment 2", 5)
    reply = say(client, "finished the dbms assignment")
    assert reply["text"] == "Which one did you finish?"
    assert len(reply["tasks"]) == 2


# -- files ------------------------------------------------------------------------------


def _doc(session, settings, title, subject_id, doc_type=DocType.notes):
    path = settings.library_root / f"{title}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4")
    d = Document(sha256=title, original_path=str(path), current_path=str(path),
                 filename=path.name, title=title, subject_id=subject_id, doc_type=doc_type,
                 status=DocStatus.organized)
    session.add(d)
    session.commit()
    return d


def test_find_and_open_files(client, session, settings, opened):
    dbms = Subject(name="Database Management Systems", aliases=["DBMS"])
    session.add(dbms)
    session.commit()
    _doc(session, settings, "Module 3", dbms.id)
    _doc(session, settings, "Module 4", dbms.id)
    _doc(session, settings, "DBMS 2024", dbms.id, DocType.question_paper)

    reply = say(client, "find my DBMS notes")
    assert sorted(f["title"] for f in reply["files"]) == ["Module 3", "Module 4"]

    reply = say(client, "open my dbms question paper")
    assert reply["text"] == "Opening “DBMS 2024”."
    assert opened[0][1].endswith("DBMS 2024.pdf")


def test_organise_starts_a_scan(client, monkeypatch):
    from contextos.ingest import jobs

    monkeypatch.setattr(jobs.scan_job, "request", lambda **kw: True)
    assert say(client, "organise my files")["text"].startswith("On it!")


# -- conversation & the LLM -----------------------------------------------------------------


def test_greeting_uses_the_briefing(client):
    reply = say(client, "hi khushi")
    assert "I'm Khushi" in reply["text"] and reply["suggestions"]


def test_unknown_request_without_llm_offers_suggestions(client):
    reply = say(client, "what is a deadlock")
    assert "not sure" in reply["text"] and reply["suggestions"]


def test_llm_answers_study_questions(client):
    llm.set_llm(FakeLLM({"reply": "A deadlock is when processes wait on each other forever.",
                         "action": "none"}))
    reply = say(client, "what is a deadlock")
    assert reply["text"].startswith("A deadlock is") and reply["by"] == "fake"


def test_llm_can_choose_an_action_and_khushi_reports_the_real_result(client, opened):
    llm.set_llm(FakeLLM({"reply": "Done! I played it.", "action": "play",
                         "target": "rain sounds", "where": "youtube"}))
    reply = say(client, "I can't focus, put something calming on")
    assert reply["text"] == "Here's “rain sounds” on YouTube. Pick one to start it."
    assert opened == [("open", "https://www.youtube.com/results?search_query=rain+sounds")]


def test_vague_follow_up_goes_to_the_llm_with_history(client, opened):
    fake = FakeLLM({"reply": "Searching!", "action": "search", "target": "black holes",
                    "where": "wikipedia"})
    llm.set_llm(fake)
    fake.reply = {"reply": "Black holes are regions of spacetime...", "action": "none"}
    say(client, "tell me about black holes")
    fake.reply = {"reply": "Searching!", "action": "search", "target": "black holes",
                  "where": "wikipedia"}
    say(client, "search me this on wikipedia")
    assert "Student: tell me about black holes" in fake.prompts[-1]
    assert opened == [("open", "https://en.wikipedia.org/wiki/Special:Search?search=black+holes")]


def test_llm_trouble_still_gets_a_helpful_answer(client):
    from contextos.llm import LLMUnavailable

    llm.set_llm(FakeLLM(LLMUnavailable("no model could answer: quota used up")))
    reply = say(client, "what is a deadlock")
    assert "taking a break" in reply["text"] and reply["suggestions"]


def test_rules_never_spend_llm_quota(client, opened):
    fake = FakeLLM({"reply": "x", "action": "none"})
    llm.set_llm(fake)
    say(client, "open youtube")
    say(client, "what's due this week")
    assert fake.prompts == []


def test_history_and_clear(client, opened):
    say(client, "open youtube")
    history = client.get("/api/chat").json()
    assert [(m["role"], m["text"]) for m in history] == [
        ("user", "open youtube"), ("khushi", "Opening Youtube.")]
    assert history[1]["actions"][0]["label"] == "Opened Youtube"
    assert client.delete("/api/chat").status_code == 204
    assert client.get("/api/chat").json() == []


def test_task_cards_show_current_state(client, session):
    t = _add(session, "OS Lab", 2)
    say(client, "my assignments")
    t.status = TaskStatus.done
    session.add(t)
    session.commit()
    assert client.get("/api/chat").json()[-1]["tasks"][0]["status"] == "done"


def test_empty_message_is_rejected(client):
    assert client.post("/api/chat", json={"text": "   "}).status_code == 422


def test_chat_saves_both_messages(client, session):
    from contextos.models import ChatMessage

    say(client, "thanks")
    assert [m.role for m in session.exec(select(ChatMessage))] == ["user", "khushi"]


def test_every_rule_ignores_case():
    import re

    from contextos.agent.intents import RULES

    assert [name for name, p in RULES if not p.flags & re.I] == []
