"""Shapes the API returns, shared by the organiser and files endpoints."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel
from sqlmodel import Session, select

from contextos.config import get_settings
from contextos.models import DocStatus, DocType, Document, Subject, Task, TaskStatus


class DeadlineOut(BaseModel):
    id: int
    title: str
    due_at: datetime | None
    status: TaskStatus


class DocumentOut(BaseModel):
    id: int
    filename: str
    current_path: str
    planned_path: str | None
    # planned_path relative to the library root, for display. Always "/"-separated,
    # even on Windows: the Organize page splits it into Semester / Subject / Type.
    destination: str | None
    doc_type: DocType
    subject_id: int | None
    subject: str | None
    subject_color: str | None
    title: str | None
    semester: str | None
    confidence: float
    classified_by: str | None
    extraction: str | None
    error: str | None
    status: DocStatus
    deadlines: list[DeadlineOut]
    updated_at: datetime


def _relative(path: str | None, root: Path) -> str | None:
    if not path:
        return None
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return path


def documents_out(session: Session, docs: list[Document]) -> list[DocumentOut]:
    root = get_settings().library_root
    subjects = {s.id: s for s in session.exec(select(Subject)).all()}
    ids = [d.id for d in docs]
    tasks: dict[int, list[DeadlineOut]] = {}
    if ids:
        for t in session.exec(select(Task).where(Task.source_document_id.in_(ids))).all():
            tasks.setdefault(t.source_document_id, []).append(
                DeadlineOut(id=t.id, title=t.title, due_at=t.due_at, status=t.status))
    out = []
    for d in docs:
        s = subjects.get(d.subject_id)
        out.append(DocumentOut(
            id=d.id, filename=d.filename, current_path=d.current_path,
            planned_path=d.planned_path, destination=_relative(d.planned_path, root),
            doc_type=d.doc_type, subject_id=d.subject_id, subject=s.name if s else None,
            subject_color=s.color if s else None, title=d.title, semester=d.semester,
            confidence=d.confidence, classified_by=d.classified_by, extraction=d.extraction,
            error=d.error, status=d.status, deadlines=tasks.get(d.id, []),
            updated_at=d.updated_at,
        ))
    return out
