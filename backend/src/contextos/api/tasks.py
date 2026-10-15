"""Assignments & deadlines: the Tasks page, to-do steps, and Khushi's briefing."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from contextos.agent.khushi import NAME, build_briefing
from contextos.agent.notify import notifications_available, notify
from contextos.config import get_settings
from contextos.db import get_session
from contextos.ingest.pipeline import get_or_create_subject
from contextos.llm import get_llm
from contextos.models import Document, Subject, Task, TaskSource, TaskStatus, TaskStep
from contextos.tasks.service import (
    days_left,
    delete_task,
    set_due,
    set_status,
    steps_for,
)
from contextos.tasks.steps import generate_steps

router = APIRouter(tags=["tasks"])


class StepOut(BaseModel):
    id: int
    text: str
    done: bool
    written_by: str


class TaskOut(BaseModel):
    id: int
    title: str
    notes: str | None
    subject_id: int | None
    subject: str | None
    subject_color: str | None
    due_at: datetime | None
    days_left: int | None
    status: TaskStatus
    source: TaskSource
    document_id: int | None
    document_name: str | None
    steps: list[StepOut]
    completed_at: datetime | None


class TaskIn(BaseModel):
    title: str
    subject: str | None = None
    due_date: date | None = None
    notes: str | None = None


class TaskEdit(BaseModel):
    title: str | None = None
    subject: str | None = None  # "" clears it
    due_date: date | None = None  # send null to clear
    notes: str | None = None
    status: TaskStatus | None = None


class StepIn(BaseModel):
    text: str


class StepEdit(BaseModel):
    text: str | None = None
    done: bool | None = None


class LineOut(BaseModel):
    text: str
    link: str | None
    tone: str


class BriefingOut(BaseModel):
    name: str
    greeting: str
    lines: list[LineOut]
    counts: dict[str, int]


def tasks_out(session: Session, tasks: list[Task]) -> list[TaskOut]:
    today = date.today()
    subjects = {s.id: s for s in session.exec(select(Subject)).all()}
    doc_ids = [t.source_document_id for t in tasks if t.source_document_id]
    docs = {d.id: d for d in session.exec(select(Document).where(Document.id.in_(doc_ids)))} \
        if doc_ids else {}
    steps = steps_for(session, [t.id for t in tasks])
    out = []
    for t in tasks:
        s = subjects.get(t.subject_id)
        d = docs.get(t.source_document_id)
        out.append(TaskOut(
            id=t.id, title=t.title, notes=t.notes, subject_id=t.subject_id,
            subject=s.name if s else None, subject_color=s.color if s else None,
            due_at=t.due_at, days_left=days_left(t, today), status=t.status, source=t.source,
            document_id=d.id if d else None, document_name=d.filename if d else None,
            steps=[StepOut(id=x.id, text=x.text, done=x.done, written_by=x.written_by)
                   for x in steps.get(t.id, [])],
            completed_at=t.completed_at,
        ))
    return out


def _task(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    return task


def _one(session: Session, task: Task) -> TaskOut:
    session.commit()
    session.refresh(task)
    return tasks_out(session, [task])[0]


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(session: Session = Depends(get_session)) -> list[TaskOut]:
    tasks = session.exec(select(Task).where(Task.status != TaskStatus.dismissed)).all()
    # Soonest first; undated last; done ones by when they were finished.
    tasks = sorted(tasks, key=lambda t: (t.due_at is None, t.due_at or datetime.max, t.id))
    return tasks_out(session, tasks)


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(body: TaskIn, session: Session = Depends(get_session)) -> TaskOut:
    if not body.title.strip():
        raise HTTPException(422, "title is required")
    task = Task(title=body.title.strip()[:120], notes=body.notes, source=TaskSource.manual,
                status=TaskStatus.todo)
    if body.subject and body.subject.strip():
        task.subject_id = get_or_create_subject(session, body.subject).id
    set_due(task, body.due_date)
    session.add(task)
    return _one(session, task)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def edit_task(task_id: int, body: TaskEdit, session: Session = Depends(get_session)) -> TaskOut:
    task = _task(session, task_id)
    given = body.model_fields_set
    if body.title is not None and body.title.strip():
        task.title = body.title.strip()[:120]
    if body.notes is not None:
        task.notes = body.notes or None
    if body.subject is not None:
        task.subject_id = get_or_create_subject(session, body.subject).id \
            if body.subject.strip() else None
    if "due_date" in given:
        set_due(task, body.due_date)
        # Answering Khushi's "when is it due?" (or confirming her date) accepts the task.
        if task.status == TaskStatus.suggested and body.status is None:
            set_status(session, task, TaskStatus.todo)
    if body.status is not None:
        set_status(session, task, body.status)
    session.add(task)
    return _one(session, task)


@router.delete("/tasks/{task_id}", status_code=204)
def remove_task(task_id: int, session: Session = Depends(get_session)) -> None:
    """Manual tasks are deleted. Ones found in files are dismissed, so a rescan
    does not suggest them again."""
    task = _task(session, task_id)
    if task.source == TaskSource.manual:
        delete_task(session, task)
    else:
        set_status(session, task, TaskStatus.dismissed)
    session.commit()


@router.post("/tasks/{task_id}/steps/generate", response_model=TaskOut)
def make_steps(task_id: int, replace: bool = False,
               session: Session = Depends(get_session)) -> TaskOut:
    """Khushi writes a to-do list for the assignment (AI if available, else rules)."""
    task = _task(session, task_id)
    existing = session.exec(select(TaskStep).where(TaskStep.task_id == task.id)).all()
    if existing and not replace:
        raise HTTPException(409, "this task already has a to-do list")

    text = ""
    doc = session.get(Document, task.source_document_id) if task.source_document_id else None
    if doc is not None:
        text = _document_text(doc)
    subject = session.get(Subject, task.subject_id) if task.subject_id else None
    settings = get_settings()
    steps, by, _error = generate_steps(
        title=task.title, subject=subject.name if subject else None, due_at=task.due_at,
        text=text, llm=get_llm(), snippet_chars=settings.llm_snippet_chars,
    )
    for s in existing:
        session.delete(s)
    for i, text_ in enumerate(steps):
        session.add(TaskStep(task_id=task.id, text=text_, position=i, written_by=by))
    return _one(session, task)


def _document_text(doc: Document) -> str:
    from contextos.ingest.extract import extract

    path = Path(doc.current_path)
    if path.is_file():
        return extract(path).text
    return doc.text_snippet


@router.post("/tasks/{task_id}/steps", response_model=TaskOut, status_code=201)
def add_step(task_id: int, body: StepIn, session: Session = Depends(get_session)) -> TaskOut:
    task = _task(session, task_id)
    if not body.text.strip():
        raise HTTPException(422, "step text is required")
    count = len(session.exec(select(TaskStep).where(TaskStep.task_id == task.id)).all())
    session.add(TaskStep(task_id=task.id, text=body.text.strip()[:200], position=count))
    return _one(session, task)


@router.patch("/tasks/steps/{step_id}", response_model=TaskOut)
def edit_step(step_id: int, body: StepEdit, session: Session = Depends(get_session)) -> TaskOut:
    step = session.get(TaskStep, step_id)
    if step is None:
        raise HTTPException(404, "step not found")
    if body.text is not None and body.text.strip():
        step.text = body.text.strip()[:200]
    if body.done is not None:
        step.done = body.done
    session.add(step)
    return _one(session, _task(session, step.task_id))


@router.delete("/tasks/steps/{step_id}", response_model=TaskOut)
def delete_step(step_id: int, session: Session = Depends(get_session)) -> TaskOut:
    step = session.get(TaskStep, step_id)
    if step is None:
        raise HTTPException(404, "step not found")
    task = _task(session, step.task_id)
    session.delete(step)
    return _one(session, task)


@router.post("/tasks/test-notification")
def test_notification() -> dict:
    ok = notify(f"Hi, I'm {NAME}!", "Reminders are working. I'll tap you on the shoulder "
                "before your deadlines.")
    return {"sent": ok, "available": notifications_available()}


@router.get("/khushi/briefing", response_model=BriefingOut)
def briefing(session: Session = Depends(get_session)) -> BriefingOut:
    b = build_briefing(session, datetime.now())
    return BriefingOut(name=NAME, greeting=b.greeting, counts=b.counts,
                       lines=[LineOut(**line.__dict__) for line in b.lines])
