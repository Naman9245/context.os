"""Khushi - the assistant's voice.

Her briefing is built from rules over the database, not the LLM: it is
shown on every page load, so it must be instant and must not spend quota.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, func, select

from contextos.models import DocStatus, Document, Task, TaskStatus
from contextos.tasks.service import short_date

NAME = "Khushi"


@dataclass
class Line:
    text: str
    link: str | None = None
    tone: str = "info"  # info | warn | good


@dataclass
class Briefing:
    greeting: str
    lines: list[Line] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def greeting(now: datetime) -> str:
    if now.hour < 5:
        part = "Still up? Hi"
    elif now.hour < 12:
        part = "Good morning"
    elif now.hour < 17:
        part = "Good afternoon"
    else:
        part = "Good evening"
    return f"{part}! I'm {NAME}."


def _day(dt: datetime, now: datetime) -> str:
    left = (dt.date() - now.date()).days
    if left == 0:
        return "today"
    if left == 1:
        return "tomorrow"
    return short_date(dt)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def build_briefing(session: Session, now: datetime) -> Briefing:
    today = now.date()
    pending_files = session.exec(select(func.count()).select_from(Document)
                                 .where(Document.status == DocStatus.planned)).one()
    tasks = session.exec(select(Task).where(Task.status.in_(
        [TaskStatus.suggested, TaskStatus.todo]))).all()

    to_confirm = [t for t in tasks if t.status == TaskStatus.suggested and t.due_at]
    no_deadline = [t for t in tasks if t.status == TaskStatus.suggested and not t.due_at]
    todo = sorted((t for t in tasks if t.status == TaskStatus.todo and t.due_at),
                  key=lambda t: t.due_at)
    overdue = [t for t in todo if t.due_at.date() < today]
    this_week = [t for t in todo if 0 <= (t.due_at.date() - today).days <= 7]

    b = Briefing(greeting=greeting(now), counts={
        "pending_files": pending_files, "to_confirm": len(to_confirm),
        "no_deadline": len(no_deadline), "overdue": len(overdue), "this_week": len(this_week),
    })

    if overdue:
        names = ", ".join(t.title for t in overdue[:2])
        b.lines.append(Line(f"{names} {'is' if len(overdue) == 1 else 'are'} overdue. "
                            "Let's finish it today, or update the date.", "/tasks", "warn"))
    if this_week:
        items = ", ".join(f"{t.title} ({_day(t.due_at, now)})" for t in this_week[:3])
        more = f" and {len(this_week) - 3} more" if len(this_week) > 3 else ""
        b.lines.append(Line(f"Due this week: {items}{more}.", "/tasks"))
    if no_deadline:
        if len(no_deadline) == 1:
            text = f"I couldn't find a deadline in {no_deadline[0].title}. When is it due?"
        else:
            text = (f"{_plural(len(no_deadline), 'assignment')} have no deadline written in "
                    "them. Tell me when they're due and I'll remind you.")
        b.lines.append(Line(text, "/tasks", "warn"))
    if to_confirm:
        b.lines.append(Line(f"I spotted {_plural(len(to_confirm), 'deadline')} in your files. "
                            "Can you check I got them right?", "/tasks"))
    if pending_files:
        b.lines.append(Line(f"{_plural(pending_files, 'new file')} "
                            f"{'is' if pending_files == 1 else 'are'} waiting. "
                            "Want me to sort them?", "/organize"))
    if not b.lines:
        b.lines.append(Line("You're all caught up. Nice work!", None, "good"))
    return b
