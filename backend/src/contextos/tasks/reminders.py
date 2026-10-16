"""Khushi's deadline reminders: N days before (default 5 and 3), each sent once.

If the laptop was off when a reminder was due, the next check sends a single
catch-up ("due in 2 days") rather than every missed one at once.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import date, datetime

from sqlmodel import Session, select

from contextos.models import Subject, Task, TaskStatus, TaskStep
from contextos.tasks.service import long_date

log = logging.getLogger(__name__)

Send = Callable[[str, str], bool]


def pending_offsets(task: Task, today: date, offsets: list[int]) -> list[int]:
    """Reminder offsets that are now due for this task and not yet sent."""
    if task.status != TaskStatus.todo or task.due_at is None:
        return []
    left = (task.due_at.date() - today).days
    if left < 0:
        return []
    sent = set(task.reminded_days or [])
    return [d for d in offsets if left <= d and d not in sent]


def _when(left: int) -> str:
    if left == 0:
        return "today"
    if left == 1:
        return "tomorrow"
    return f"in {left} days"


def reminder_text(task: Task, today: date, subject: str | None, done: int, total: int
                  ) -> tuple[str, str]:
    left = (task.due_at.date() - today).days
    title = f"{task.title} is due {_when(left)}"
    parts = [f"Due {long_date(task.due_at)}."]
    if subject:
        parts.insert(0, f"{subject}.")
    if total:
        parts.append(f"You've done {done} of {total} steps." if done
                     else f"Your to-do list has {total} steps - start with the first one!")
    return title, " ".join(parts)


def run_reminders(session: Session, *, now: datetime, offsets: list[int], send: Send
                  ) -> list[str]:
    """Send every reminder that is due. Returns the titles sent."""
    today = now.date()
    sent_titles = []
    tasks = session.exec(select(Task).where(Task.status == TaskStatus.todo,
                                            Task.due_at != None)).all()  # noqa: E711
    for task in tasks:
        pending = pending_offsets(task, today, offsets)
        if not pending:
            continue
        subject = session.get(Subject, task.subject_id) if task.subject_id else None
        steps = session.exec(select(TaskStep).where(TaskStep.task_id == task.id)).all()
        title, body = reminder_text(task, today, subject.name if subject else None,
                                    sum(s.done for s in steps), len(steps))
        if send(title, body):
            task.reminded_days = sorted(set(task.reminded_days or []) | set(pending))
            session.add(task)
            session.commit()
            sent_titles.append(title)
    return sent_titles


class ReminderLoop:
    """Checks for due reminders now and then every few minutes, on a daemon thread."""

    def __init__(self, check: Callable[[], object], every_seconds: float):
        self._check = check
        self._every = every_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="khushi-reminders", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._check()
            except Exception:
                log.exception("reminder check failed")
            self._stop.wait(self._every)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
