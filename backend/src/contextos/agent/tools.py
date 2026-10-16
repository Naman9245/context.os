"""What Khushi can actually do. Rules and the LLM both end up calling these.

Every method returns a Reply with the text Khushi says, what she did, and
any tasks or files to show as cards. Replies are written from real results
(never from what the LLM imagined happened).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from sqlmodel import Session, select

from contextos.agent import actions
from contextos.agent.apps import (
    ENGINE_ALIASES,
    find_app,
    find_site,
    installed_command,
    search_url,
)
from contextos.agent.music import VIDEO_WORDS, music_query, resolve_name, same_name
from contextos.config import Settings
from contextos.ingest.classify import match_subject
from contextos.ingest.pipeline import subject_refs
from contextos.llm import LLMProvider
from contextos.models import DocStatus, DocType, Document, Subject, Task, TaskSource, TaskStatus
from contextos.tasks.deadlines import parse_when
from contextos.tasks.service import days_left, long_date, set_due, set_status


@dataclass
class Reply:
    text: str
    actions: list[dict] = field(default_factory=list)  # {"label", "ok", "url"?}
    task_ids: list[int] = field(default_factory=list)
    doc_ids: list[int] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    by: str = "rules"
    # True when the rules could not resolve the request - worth asking the LLM.
    unresolved: bool = False
    # What this reply produced, so the next message can refer to it ("open it",
    # "mark it done", "not on YouTube - on Spotify"). A dict with a "kind":
    # search/play {query, where}, files {doc_ids}, tasks {task_ids}, page {title, url}.
    context: dict | None = None

    def payload(self) -> dict:
        p = {"actions": self.actions, "task_ids": self.task_ids, "doc_ids": self.doc_ids,
             "suggestions": self.suggestions, "by": self.by}
        if self.context:
            p["context"] = self.context
        return p


SUGGESTIONS = ["What's due this week?", "Open Spotify", "Play lofi on YouTube",
               "Search black holes on Wikipedia", "Organise my files"]

STOP = {"the", "my", "a", "an", "for", "of", "to", "and", "on", "in", "all", "me", "with",
        "file", "files", "pdf", "pdfs", "document", "documents", "please"}
TYPE_WORDS = {
    DocType.notes: {"note", "notes"},
    DocType.question_paper: {"question", "questions", "paper", "papers", "qp", "pyq", "exam"},
    DocType.slides: {"slide", "slides", "ppt", "presentation", "lecture"},
    DocType.lab: {"lab", "manual", "record", "practical", "experiment"},
    DocType.assignment: {"assignment", "assignments", "homework"},
    DocType.syllabus: {"syllabus"},
    DocType.notice: {"notice", "notices", "circular"},
}
# Words that only make sense with the conversation ("search me THIS") - the LLM's job.
VAGUE = {"this", "that", "it", "these", "those"}



def _norm(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def tokens(text: str) -> set[str]:
    return {_norm(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


def _match(query: set[str], candidate: set[str]) -> float:
    return len(query & candidate) / len(query) if query else 0.0


def is_vague(query: str | None) -> bool:
    return not query or query.strip().lower() in VAGUE


class Tools:
    def __init__(self, session: Session, settings: Settings, now: datetime,
                 llm: LLMProvider | None = None):
        self.session = session
        self.settings = settings
        self.now = now
        self.today = now.date()
        self.llm = llm

    # -- apps, websites, web ------------------------------------------------------

    @staticmethod
    def _failed(what: str, error: Exception) -> Reply:
        """Say plainly that something did not open - never claim it did."""
        return Reply(f"I tried to open {what}, but it closed straight away ({error}).",
                     actions=[{"label": f"Couldn't open {what}", "ok": False}])

    def open(self, target: str) -> Reply:
        target = target.strip()
        if target.lower().startswith(("my ", "the ")):
            return self.find_files(target.split(" ", 1)[1], open_best=True)
        app = find_app(target)
        if app is not None:
            try:
                how = actions.launch_app(app)
            except actions.ActionNotAllowed as e:
                return Reply(f"Sorry, {e}.", actions=[{"label": f"Open {app.name}", "ok": False}])
            except actions.LaunchFailed as e:
                return self._failed(app.name, e)
            if how == "web":
                return Reply(f"{app.name} isn't installed, so I opened it in your browser.",
                             actions=[{"label": f"Opened {app.name} (web)", "ok": True,
                                       "url": app.web}])
            return Reply(f"Opening {app.name}!", actions=[{"label": f"Opened {app.name}",
                                                           "ok": True}],
                         context={"kind": "site", "where": app.key})
        url = find_site(target)
        if url is not None:
            name = target if "." in target else target.title()
            try:
                actions.open_url(url)
            except actions.LaunchFailed as e:
                return self._failed(name, e)
            return Reply(f"Opening {name}.", actions=[{"label": f"Opened {name}", "ok": True,
                                                       "url": url}],
                         context={"kind": "site", "url": url,
                                  "where": ENGINE_ALIASES.get(target.lower())})
        found = self.find_files(target, open_best=True)
        if found.doc_ids:
            return found
        return Reply(f"I don't know an app, website or file called “{target}”.",
                     suggestions=["Open Spotify", "Open YouTube", "Find my notes"],
                     unresolved=True)

    def search(self, query: str, where: str = "google") -> Reply:
        if is_vague(query) or query.strip().lower() in ("something", "anything"):
            return Reply("What should I search for?", unresolved=True)
        label, url = search_url(where, query)
        try:
            actions.open_url(url)
        except actions.LaunchFailed as e:
            return self._failed("the browser", e)
        return Reply(f"Searching {label} for “{query}”.",
                     actions=[{"label": f"{label}: {query}", "ok": True, "url": url}],
                     context={"kind": "search", "query": query, "where": label.lower()})

    @staticmethod
    def _spotify_installed() -> bool:
        app = find_app("spotify")
        return app is not None and installed_command(app) is not None

    def play(self, query: str, where: str | None = None, *, resolve: bool = True) -> Reply:
        """Music on Spotify when it is installed, videos (and everything else) on YouTube.

        `resolve` checks artist/song names the voice typing may have misheard
        ("hairstyle" -> "Harry Styles"); off when the LLM already chose the query.
        """
        if is_vague(query):
            return Reply("What would you like me to play?", unresolved=True)
        heard = query
        video = bool(VIDEO_WORDS.search(query))
        if where is None:
            where = "youtube" if video or not self._spotify_installed() else "spotify"
        if not video:
            query = music_query(query)
        checked = resolve_name(query, self.llm) if resolve else query
        # Say so when a name was corrected, so a wrong guess is easy to spot and fix.
        aside = "" if same_name(checked, query) else f" (I heard “{heard}”)"
        query = checked
        context = {"kind": "play", "query": query, "where": where}
        if where == "spotify":
            if self._spotify_installed():
                try:
                    actions.open_url(f"spotify:search:{quote(query)}")
                except actions.LaunchFailed as e:
                    return self._failed("Spotify", e)
                return Reply(f"Opening “{query}” in Spotify{aside}. Pick a playlist or song to "
                             "start it.", actions=[{"label": f"Spotify: {query}", "ok": True}],
                             context=context)
            label, url = search_url("spotify", query)
        else:
            label, url = search_url("youtube", query)
        try:
            actions.open_url(url)
        except actions.LaunchFailed as e:
            return self._failed(label, e)
        return Reply(f"Here's “{query}” on {label}{aside}. Pick one to start it.",
                     actions=[{"label": f"{label}: {query}", "ok": True, "url": url}],
                     context=context)

    def redo(self, last: dict, target: str) -> Reply:
        """Repeat the last play/search on the service the user corrected to."""
        if target == "spotify" or (target == "youtube" and last.get("kind") == "play"):
            return self.play(last["query"], target, resolve=False)  # already checked
        return self.search(last["query"], target)

    # -- "it": the thing just shown --------------------------------------------------

    def open_result(self, ctx: dict | None) -> Reply:
        """'open it' / 'play the first one': the first of whatever was just shown."""
        kind = (ctx or {}).get("kind")
        if kind == "files" and ctx.get("doc_ids"):
            doc = self.session.get(Document, ctx["doc_ids"][0])
            if doc is not None:
                return self._open_doc(doc)
        if kind == "tasks" and len(ctx.get("task_ids", [])) == 1:
            task = self.session.get(Task, ctx["task_ids"][0])
            doc = self.session.get(Document, task.source_document_id) \
                if task and task.source_document_id else None
            if doc is not None:
                return self._open_doc(doc)
        if kind in ("search", "play"):
            return self._open_first_result(ctx)
        return Reply("What should I open?", unresolved=True)

    def _open_doc(self, doc: Document) -> Reply:
        try:
            actions.open_path(Path(doc.current_path),
                              [self.settings.library_root, *self.settings.watch_dirs])
        except (actions.ActionNotAllowed, actions.LaunchFailed, FileNotFoundError):
            return Reply(f"I found “{doc.title}” but couldn't open it.", doc_ids=[doc.id])
        return Reply(f"Opening “{doc.title}”.", doc_ids=[doc.id],
                     actions=[{"label": f"Opened {doc.title}", "ok": True}],
                     context={"kind": "files", "doc_ids": [doc.id]})

    def _open_first_result(self, ctx: dict) -> Reply:
        from contextos.browser import bridge

        where = ctx.get("where") or "google"
        if where == "spotify":
            return Reply("Pick a song in Spotify's results - I can't press play inside the "
                         "Spotify app yet.")
        site = {"youtube": "youtube.com", "google": "google.com",
                "wikipedia": "wikipedia.org"}.get(where)
        if site is None:
            return Reply(f"I can't pick results on {where.title()} yet - click the one you "
                         "want.")
        result = bridge.open_first(site)
        if result is None:
            return Reply("I can't see the results page myself, so I don't know which one is "
                         "first. Click it - or install Khushi for Chrome (Settings) and I'll "
                         "open it for you next time.")
        if not result.get("ok"):
            return Reply("I couldn't find a result to open on that page. Is it still open?")
        title = result.get("title") or "the first result"
        return Reply(f"Opening “{title}”.",
                     actions=[{"label": f"Opened {title}", "ok": True, "url": result.get("url")}],
                     context={"kind": "page", "title": title, "url": result.get("url")})

    def complete_in_context(self, ctx: dict | None) -> Reply:
        """'mark it done' right after Khushi showed exactly one assignment."""
        c = ctx or {}
        ids = c.get("task_ids", []) if c.get("kind") == "tasks" else []
        task = self.session.get(Task, ids[0]) if len(ids) == 1 else None
        if task is None or task.status == TaskStatus.done:
            return Reply("Which assignment did you finish?", unresolved=True)
        set_status(self.session, task, TaskStatus.done)
        self.session.commit()
        return Reply(f"Nice work! I've marked “{task.title}” as finished.",
                     actions=[{"label": f"Finished {task.title}", "ok": True}])

    # -- assignments ------------------------------------------------------------------

    def _open_tasks(self) -> list[Task]:
        return list(self.session.exec(select(Task).where(Task.status == TaskStatus.todo)).all())

    def list_tasks(self, when: str | None = None) -> Reply:
        tasks = sorted(self._open_tasks(),
                       key=lambda t: (t.due_at is None, t.due_at or datetime.max))
        windows = {
            "today": (lambda d: d is not None and d <= 0, "today"),
            "tomorrow": (lambda d: d == 1, "tomorrow"),
            "this week": (lambda d: d is not None and d <= 7, "this week"),
            "soon": (lambda d: d is not None and d <= 7, "soon"),
            "next week": (lambda d: d is not None and 8 <= d <= 14, "next week"),
            "overdue": (lambda d: d is not None and d < 0, "overdue"),
            "late": (lambda d: d is not None and d < 0, "overdue"),
        }
        if when in windows:
            test, label = windows[when]
            tasks = [t for t in tasks if test(days_left(t, self.today))]
        else:
            label = None
        waiting = self.session.exec(select(Task).where(Task.status == TaskStatus.suggested)).all()
        note = (f" {len(waiting)} more {'needs' if len(waiting) == 1 else 'need'} your answer "
                "on the Assignments page.") if waiting else ""

        if not tasks:
            text = (f"Nothing {'is ' if label == 'overdue' else 'due '}{label}. Nice!"
                    if label else "You don't have any open assignments. Nice!")
            return Reply(text + note, suggestions=["Add an assignment", "What's due next week?"])
        n = len(tasks)
        if label == "overdue":
            head = f"{n} {'thing is' if n == 1 else 'things are'} overdue:"
        elif label:
            head = f"You have {n} {'thing' if n == 1 else 'things'} due {label}:"
        else:
            head = f"Here {'is' if n == 1 else 'are'} your {n} open assignment{'s' * (n != 1)}:"
        ids = [t.id for t in tasks][:10]
        return Reply(head + note, task_ids=ids, context={"kind": "tasks", "task_ids": ids})

    def _task_tokens(self, t: Task, subjects: dict[int, Subject]) -> set[str]:
        s = subjects.get(t.subject_id)
        extra = " ".join([s.name, s.code or "", *(s.aliases or [])]) if s else ""
        return tokens(f"{t.title} {extra}")

    def complete_task(self, query: str) -> Reply:
        subjects = {s.id: s for s in self.session.exec(select(Subject)).all()}
        q = tokens(query)
        open_tasks = list(self.session.exec(select(Task).where(
            Task.status.in_([TaskStatus.todo, TaskStatus.suggested]))).all())
        scored = sorted(((_match(q, self._task_tokens(t, subjects)), t) for t in open_tasks),
                        key=lambda x: -x[0])
        best = [t for score, t in scored if score >= 0.5 and score == scored[0][0]]
        if not best:
            return Reply(f"I couldn't find an assignment matching “{query}”.",
                         suggestions=["What's due this week?"], unresolved=True)
        if len(best) > 1:
            ids = [t.id for t in best[:5]]
            return Reply("Which one did you finish?", task_ids=ids,
                         context={"kind": "tasks", "task_ids": ids})
        task = best[0]
        set_status(self.session, task, TaskStatus.done)
        self.session.commit()
        return Reply(f"Nice work! I've marked “{task.title}” as finished.",
                     actions=[{"label": f"Finished {task.title}", "ok": True}])

    def add_task(self, text: str, due_iso: str | None = None) -> Reply:
        due, title = parse_when(text, self.today, self.settings.date_order)
        if due_iso and due is None:
            due, _ = parse_when(due_iso, self.today, self.settings.date_order)
        title = re.sub(r"^(to|that i|i need to|i have to)\s+", "", title, flags=re.I).strip()
        if not title:
            return Reply("What should I add?", unresolved=True)
        title = title[0].upper() + title[1:]
        task = Task(title=title[:120], source=TaskSource.chat, status=TaskStatus.todo)
        subject, score = match_subject(title, "", subject_refs(self.session))
        if subject is not None and score >= 0.6:
            task.subject_id = subject.id
        set_due(task, due)
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        if due is None:
            return Reply(f"Added “{task.title}”. It has no deadline yet - tell me one, like "
                         f"“{task.title} due Friday”.", task_ids=[task.id])
        offsets = [str(d) for d in self.settings.reminder_days]
        days = " and ".join([", ".join(offsets[:-1]), offsets[-1]] if len(offsets) > 1
                            else offsets)
        when = long_date(due)
        return Reply(f"Added “{task.title}”, due {when}. I'll remind you {days} days before.",
                     task_ids=[task.id], actions=[{"label": f"Added {task.title}", "ok": True}])

    # -- files --------------------------------------------------------------------------

    def find_files(self, query: str, open_best: bool = False) -> Reply:
        q = tokens(query)
        if not q:
            return Reply("Which files are you looking for?", unresolved=True)
        subjects = {s.id: s for s in self.session.exec(select(Subject)).all()}
        docs = self.session.exec(select(Document).where(
            Document.status.in_([DocStatus.organized, DocStatus.planned]))).all()
        scored = []
        for d in docs:
            s = subjects.get(d.subject_id)
            words = f"{d.title or ''} {d.filename} {d.semester or ''}"
            if s:
                words += " " + " ".join([s.name, s.code or "", *(s.aliases or [])])
            candidate = tokens(words) | {_norm(w) for w in TYPE_WORDS.get(d.doc_type, set())}
            score = _match(q, candidate)
            if score >= 0.6:
                scored.append((score, d))
        scored.sort(key=lambda x: (-x[0], x[1].title or ""))
        if not scored:
            return Reply(f"I couldn't find any files matching “{query}”.",
                         suggestions=["Organise my files"], unresolved=True)

        top_score = scored[0][0]
        top = [d for score, d in scored if score == top_score]
        if open_best and len(top) == 1:
            return self._open_doc(top[0])
        ids = [d.id for _, d in scored][:8]
        more = f" (showing {len(ids)} of {len(scored)})" if len(scored) > len(ids) else ""
        return Reply(f"I found {len(scored)} file{'s' * (len(scored) != 1)}{more}:",
                     doc_ids=ids, context={"kind": "files", "doc_ids": ids})

    def organize(self) -> Reply:
        from contextos.ingest.jobs import scan_job

        started = scan_job.request()
        if not started:
            return Reply("I'm already scanning - give me a moment.")
        return Reply("On it! I'm checking your folders. New files will show up on the "
                     "Organize page for you to approve.",
                     actions=[{"label": "Started a scan", "ok": True}])
