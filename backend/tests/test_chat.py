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
    ("search games on Google in Google Chrome", "search", {"q": "games", "where": "google"}),
    ("google how to make tea", "search", {"q": "how to make tea"}),  # Google is the default
    ("play something nice in spotigfy", "play", {"q": "something nice", "where": "spotify"}),
    ("play songs in hindi", "play", {"q": "songs in hindi"}),
    ("search black holes on wikipeda", "search", {"q": "black holes", "where": "wikipedia"}),
    ("search hotels in goa", "search", {"q": "hotels in goa"}),
    ("listen to arijit singh on spotify", "play", {"q": "arijit singh", "where": "spotify"}),
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


@pytest.mark.parametrize("kind, says", [
    ("busy", "Google's AI is overloaded right now"),
    ("quota", "my free AI quota is used up"),
])
def test_llm_trouble_says_what_really_happened(client, kind, says):
    from contextos.llm import LLMUnavailable

    llm.set_llm(FakeLLM(LLMUnavailable("no model could answer", kind=kind)))
    reply = say(client, "what is a deadlock")
    assert says in reply["text"] and reply["suggestions"]


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


# -- music: the right app, typos, moods and corrections --------------------------------


def test_music_goes_to_spotify_when_it_is_installed(client, opened, installed):
    installed.add("spotify")
    say(client, "play lofi")
    assert opened == [("open", "spotify:search:lofi")]


def test_music_goes_to_youtube_without_spotify(client, opened, installed):
    say(client, "play lofi")
    assert opened == [("open", "https://www.youtube.com/results?search_query=lofi")]


def test_videos_go_to_youtube_even_with_spotify(client, opened, installed):
    installed.add("spotify")
    say(client, "play dijkstra algorithm lecture")
    assert opened[0][1].startswith("https://www.youtube.com/results?search_query=dijkstra")


def test_typo_in_the_app_name_still_means_spotify(client, opened, installed):
    installed.add("spotify")
    reply = say(client, "play something nice in spotigfy")
    assert opened == [("open", "spotify:search:chill%20vibes")]
    assert reply["text"].startswith("Opening “chill vibes” in Spotify")


@pytest.mark.parametrize("said, query", [
    ("something nice", "chill vibes"), ("some music", "chill vibes"),
    ("music for studying", "deep focus"), ("something happy", "happy hits"),
    ("lofi", "lofi"), ("arijit singh", "arijit singh"),
])
def test_moods_become_real_searches(said, query):
    from contextos.agent.music import music_query

    assert music_query(said) == query


def test_correction_repeats_the_last_request_on_the_right_app(client, opened, installed):
    installed.add("spotify")
    say(client, "play lofi beats on youtube")
    reply = say(client, "not on youtube i want start in spotify")
    assert opened[-1] == ("open", "spotify:search:lofi%20beats")
    assert reply["text"].startswith("Opening “lofi beats” in Spotify")


def test_search_correction(client, opened):
    say(client, "search black holes")
    say(client, "no, on wikipedia")
    assert opened[-1] == ("open",
                          "https://en.wikipedia.org/wiki/Special:Search?search=black+holes")


def test_open_spotify_is_not_a_correction(client, opened, installed):
    installed.add("spotify")
    say(client, "play lofi on youtube")
    say(client, "open spotify")
    assert opened[-1] == ("spawn", "/usr/bin/spotify")  # just opens the app


def test_correction_with_nothing_to_correct_is_not_guessed(client, opened):
    fake = FakeLLM({"reply": "What should I put on?", "action": "none"})
    llm.set_llm(fake)
    reply = say(client, "on spotify instead")
    assert opened == [] and reply["text"] == "What should I put on?"


# -- misheard names ("Harry Styles" heard as "hairstyle") ------------------------------


def test_misheard_artist_is_understood(client, opened, installed):
    installed.add("spotify")
    llm.set_llm(FakeLLM({"query": "Harry Styles"}))
    reply = say(client, "can you like play hairstyle in spotify")
    assert opened == [("open", "spotify:search:Harry%20Styles")]
    assert reply["text"].startswith("Opening “Harry Styles” in Spotify (I heard “hairstyle”)")


def test_correct_names_get_no_i_heard_note(client, opened, installed):
    installed.add("spotify")
    llm.set_llm(FakeLLM({"query": "Arijit Singh"}))
    reply = say(client, "play arijit singh")
    assert opened == [("open", "spotify:search:Arijit%20Singh")]
    assert "I heard" not in reply["text"]


def test_genres_and_moods_never_spend_ai_quota(client, opened, installed):
    installed.add("spotify")
    fake = FakeLLM({"query": "should not be used"})
    llm.set_llm(fake)
    for said in ("play lofi", "play something nice", "play hindi songs", "play rain sounds"):
        say(client, said)
    assert fake.prompts == []


def test_ai_trouble_plays_what_was_said(client, opened, installed):
    from contextos.llm import LLMUnavailable

    installed.add("spotify")
    llm.set_llm(FakeLLM(LLMUnavailable("busy", kind="busy")))
    reply = say(client, "play hairstyle on spotify")
    assert opened == [("open", "spotify:search:hairstyle")]
    assert "I heard" not in reply["text"]


def test_a_rambling_ai_answer_is_ignored():
    from contextos.agent.music import resolve_name

    rambling = FakeLLM({"query": "I think you might mean the British singer Harry Styles, "
                                 "who rose to fame with One Direction and later went solo"})
    assert resolve_name("hairstyle", rambling) == "hairstyle"


def test_a_correction_does_not_check_the_name_again(client, opened, installed):
    installed.add("spotify")
    fake = FakeLLM({"query": "Harry Styles"})
    llm.set_llm(fake)
    say(client, "play hairstyle on youtube")
    calls = len(fake.prompts)
    say(client, "not on youtube, on spotify")
    assert opened[-1] == ("open", "spotify:search:Harry%20Styles")
    assert len(fake.prompts) == calls  # no second lookup


@pytest.mark.parametrize("query, generic", [
    ("lofi", True), ("hindi songs", True), ("chill vibes", True), ("90s bollywood", True),
    ("hairstyle", False), ("arijit singh", False), ("watermelon sugar", False),
])
def test_is_generic(query, generic):
    from contextos.agent.music import is_generic

    assert is_generic(query) is generic


# -- "it", steps and context: doing what was asked, start to finish ---------------------


@pytest.fixture
def extension(monkeypatch):
    """Pretend Khushi for Chrome is installed; records which sites "open it" was asked for."""
    from contextos import browser

    asked: list[str] = []

    def open_first(site):
        asked.append(site)
        return {"ok": True, "title": "PODCAST OF THE DECADE | CARRYMINATI",
                "url": "https://www.youtube.com/watch?v=abc"}

    monkeypatch.setattr(browser.bridge, "open_first", open_first)
    return asked


def test_the_three_step_request_from_the_screenshot(client, opened, extension):
    reply = say(client, "first open youtube and then search carryminati pacify and then "
                        "open the first video you see in that")
    assert opened == [
        ("open", "https://www.youtube.com"),
        ("open", "https://www.youtube.com/results?search_query=carryminati+pacify"),
    ]
    assert extension == ["youtube.com"]
    assert reply["text"].splitlines() == [
        "Opening Youtube.",
        "Searching YouTube for “carryminati pacify”.",
        "Opening “PODCAST OF THE DECADE | CARRYMINATI”.",
    ]
    assert [a["ok"] for a in reply["actions"]] == [True, True, True]


def test_without_the_extension_khushi_says_what_she_cannot_do(client, opened):
    reply = say(client, "search carryminati on youtube and then open the first video")
    assert len(opened) == 1  # the search happened
    assert "I can't see the results page myself" in reply["text"]
    assert "Khushi for Chrome" in reply["text"]


def test_after_opening_youtube_a_plain_search_happens_there(client, opened):
    say(client, "open youtube")
    say(client, "search carryminati")
    assert opened[-1] == ("open", "https://www.youtube.com/results?search_query=carryminati")


def test_a_separate_search_after_music_still_goes_to_google(client, opened):
    say(client, "play lofi on youtube")
    say(client, "search black holes")
    assert opened[-1] == ("open", "https://www.google.com/search?q=black+holes")


def test_open_the_first_after_a_search(client, opened, extension):
    say(client, "search carryminati on youtube")
    reply = say(client, "open the first")
    assert reply["text"] == "Opening “PODCAST OF THE DECADE | CARRYMINATI”."
    assert extension == ["youtube.com"]


def test_open_it_opens_the_file_just_found(client, session, settings, opened):
    dbms = Subject(name="Database Management Systems", aliases=["DBMS"])
    session.add(dbms)
    session.commit()
    _doc(session, settings, "Module 3", dbms.id)
    _doc(session, settings, "Module 4", dbms.id)
    say(client, "find my DBMS notes")
    reply = say(client, "open it")
    assert reply["text"] == "Opening “Module 3”."
    assert opened[-1][1].endswith("Module 3.pdf")


def test_mark_it_done_after_seeing_one_assignment(client, session):
    t = _add(session, "OS Lab", 2)
    say(client, "what's due this week")
    reply = say(client, "mark it as done")
    assert reply["text"] == "Nice work! I've marked “OS Lab” as finished."
    session.refresh(t)
    assert t.status == TaskStatus.done


def test_play_the_first_one_in_spotify_is_honest(client, opened, installed):
    installed.add("spotify")
    say(client, "play lofi")
    reply = say(client, "play the first one")
    assert reply["text"].startswith("Pick a song in Spotify's results")


def test_the_ai_can_choose_open_result_too(client, opened, extension):
    say(client, "search carryminati on youtube")
    llm.set_llm(FakeLLM({"reply": "On it!", "action": "open_result"}))
    reply = say(client, "go ahead and put that podcast on")
    assert reply["text"] == "Opening “PODCAST OF THE DECADE | CARRYMINATI”."


@pytest.mark.parametrize("claim", [
    "Got it! Opening the first video for you right now.",
    "Sure, playing it now!",
    "I've opened it for you.",
])
def test_khushi_never_claims_an_action_she_did_not_take(client, claim):
    llm.set_llm(FakeLLM({"reply": claim, "action": "none"}))
    reply = say(client, "do the thing with the video")
    assert reply["text"] == "Sorry, I can't do that part myself yet."


def test_honest_questions_are_not_mistaken_for_claims(client):
    llm.set_llm(FakeLLM({"reply": "Which video should I open?", "action": "none"}))
    assert say(client, "open the other one")["text"] == "Which video should I open?"


def test_a_failed_step_stops_the_rest(client, monkeypatch, opened):
    def broken(app):
        raise actions.LaunchFailed("it crashed")

    monkeypatch.setattr(actions, "launch_app", broken)
    reply = say(client, "open discord and then search memes")
    assert opened == []  # the search never ran
    assert reply["text"].endswith("I stopped there, so I didn't do: search memes.")
