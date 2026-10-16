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
from contextos.agent.apps import find_app, find_site, installed_command, search_url
from contextos.config import Settings
from contextos.ingest.classify import match_subject
from contextos.ingest.pipeline import subject_refs
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

    def payload(self) -> dict:
        return {"actions": self.actions, "task_ids": self.task_ids, "doc_ids": self.doc_ids,
                "suggestions": self.suggestions, "by": self.by}


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
VAGUE = {"this", "that", "it", "these", "those", "something", "anything"}


def _norm(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def tokens(text: str) -> set[str]:
    return {_norm(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


def _match(query: set[str], candidate: set[str]) -> float:
    return len(query & candidate) / len(query) if query else 0.0


def is_vague(query: str | None) -> bool:
    return not query or query.strip().lower() in VAGUE


class Tools:
    def __init__(self, session: Session, settings: Settings, now: datetime):
        self.session = session
        self.settings = settings
        self.now = now
        self.today = now.date()

    # -- apps, websites, web ------------------------------------------------------

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
            if how == "web":
                return Reply(f"{app.name} isn't installed, so I opened it in your browser.",
                             actions=[{"label": f"Opened {app.name} (web)", "ok": True,
                                       "url": app.web}])
            return Reply(f"Opening {app.name}!", actions=[{"label": f"Opened {app.name}",
                                                           "ok": True}])
        url = find_site(target)
        if url is not None:
            actions.open_url(url)
            name = target if "." in target else target.title()
            return Reply(f"Opening {name}.", actions=[{"label": f"Opened {name}", "ok": True,
                                                       "url": url}])
        found = self.find_files(target, open_best=True)
        if found.doc_ids:
            return found
        return Reply(f"I don't know an app, website or file called “{target}”.",
                     suggestions=["Open Spotify", "Open YouTube", "Find my notes"],
                     unresolved=True)

    def search(self, query: str, where: str = "google") -> Reply:
        if is_vague(query):
            return Reply("What should I search for?", unresolved=True)
        label, url = search_url(where, query)
        actions.open_url(url)
        return Reply(f"Searching {label} for “{query}”.",
                     actions=[{"label": f"{label}: {query}", "ok": True, "url": url}])

    def play(self, query: str, where: str = "youtube") -> Reply:
        if is_vague(query):
            return Reply("What would you like me to play?", unresolved=True)
        if where == "spotify":
            app = find_app("spotify")
            if app is not None and installed_command(app):
                actions.open_url(f"spotify:search:{quote(query)}")
                return Reply(f"Looking up “{query}” in Spotify. Pick a track to start it.",
                             actions=[{"label": f"Spotify: {query}", "ok": True}])
            label, url = search_url("spotify", query)
        else:
            label, url = search_url("youtube", query)
        actions.open_url(url)
        return Reply(f"Here's “{query}” on {label}. Pick one to start it.",
                     actions=[{"label": f"{label}: {query}", "ok": True, "url": url}])

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
        return Reply(head + note, task_ids=[t.id for t in tasks][:10])

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
            return Reply("Which one did you finish?", task_ids=[t.id for t in best[:5]])
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
            doc = top[0]
            try:
                actions.open_path(Path(doc.current_path),
                                  [self.settings.library_root, *self.settings.watch_dirs])
            except (actions.ActionNotAllowed, FileNotFoundError):
                return Reply(f"I found “{doc.title}” but couldn't open it.", doc_ids=[doc.id])
            return Reply(f"Opening “{doc.title}”.", doc_ids=[doc.id],
                         actions=[{"label": f"Opened {doc.title}", "ok": True}])
        ids = [d.id for _, d in scored][:8]
        more = f" (showing {len(ids)} of {len(scored)})" if len(scored) > len(ids) else ""
        return Reply(f"I found {len(scored)} file{'s' * (len(scored) != 1)}{more}:",
                     doc_ids=ids)

    def organize(self) -> Reply:
        from contextos.ingest.jobs import scan_job

        started = scan_job.request()
        if not started:
            return Reply("I'm already scanning - give me a moment.")
        return Reply("On it! I'm checking your folders. New files will show up on the "
                     "Organize page for you to approve.",
                     actions=[{"label": "Started a scan", "ok": True}])
