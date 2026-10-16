"""Assignment and deadline bookkeeping shared by the scanner, the API and Khushi."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlmodel import Session, select

from contextos.models import (
    ActivityEvent,
    ActivityKind,
    DocStatus,
    DocType,
    Document,
    Task,
    TaskSource,
    TaskStatus,
    TaskStep,
    utcnow,
)

# Deadlines are end-of-day: "due 24 Oct" means you have all of the 24th.
DUE_TIME = time(23, 59)


def long_date(d: date) -> str:
    """"Friday 23 October 2026" - always with the year, so nothing is ambiguous."""
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B %Y')}"


def short_date(d: date) -> str:
    """"Fri 23 Oct 2026"."""
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b %Y')}"


def due_from_date(d: date) -> datetime:
    return datetime.combine(d, DUE_TIME)


def days_left(task: Task, today: date) -> int | None:
    return (task.due_at.date() - today).days if task.due_at else None


def ensure_assignment_task(session: Session, doc: Document) -> Task | None:
    """Every assignment gets a task. One with no deadline found becomes a question
    for the user ("when is this due?") instead of silently having no date."""
    if doc.doc_type != DocType.assignment or doc.status == DocStatus.skipped:
        return None
    existing = session.exec(select(Task).where(Task.source_document_id == doc.id)).first()
    if existing is not None:
        return None
    task = Task(
        title=doc.title or doc.filename, subject_id=doc.subject_id, due_at=None,
        source=TaskSource.extracted, source_document_id=doc.id, status=TaskStatus.suggested,
        notes="No deadline found in the file.",
    )
    session.add(task)
    return task


def ensure_assignment_tasks(session: Session) -> int:
    """Backfill: assignments scanned before tasks existed get their question too."""
    docs = session.exec(select(Document).where(Document.doc_type == DocType.assignment)).all()
    created = sum(1 for d in docs if ensure_assignment_task(session, d) is not None)
    session.commit()
    return created


def drop_unanswered_question(session: Session, doc: Document) -> None:
    """A file re-labelled as not-an-assignment no longer needs a "when is it due?"."""
    for t in session.exec(select(Task).where(
            Task.source_document_id == doc.id, Task.status == TaskStatus.suggested,
            Task.due_at == None)).all():  # noqa: E711
        session.delete(t)


def set_status(session: Session, task: Task, status: TaskStatus) -> None:
    if task.status == status:
        return
    was_done = task.status == TaskStatus.done
    task.status = status
    if status == TaskStatus.done:
        task.completed_at = utcnow()
        session.add(ActivityEvent(kind=ActivityKind.task_done, ref_id=task.id))
    elif was_done:
        task.completed_at = None
        # Un-ticking must not leave a "finished" in this week's stats.
        for e in session.exec(select(ActivityEvent).where(
                ActivityEvent.kind == ActivityKind.task_done, ActivityEvent.ref_id == task.id)):
            session.delete(e)
    session.add(task)


def set_due(task: Task, due: date | None) -> None:
    new = due_from_date(due) if due else None
    if new != task.due_at:
        task.due_at = new
        task.reminded_days = []  # a new date means fresh reminders


def steps_for(session: Session, task_ids: list[int]) -> dict[int, list[TaskStep]]:
    out: dict[int, list[TaskStep]] = {}
    if task_ids:
        for s in session.exec(select(TaskStep).where(TaskStep.task_id.in_(task_ids))
                              .order_by(TaskStep.position, TaskStep.id)).all():
            out.setdefault(s.task_id, []).append(s)
    return out


def delete_task(session: Session, task: Task) -> None:
    for s in session.exec(select(TaskStep).where(TaskStep.task_id == task.id)).all():
        session.delete(s)
    set_status(session, task, TaskStatus.todo)  # clears any task_done event
    session.delete(task)
