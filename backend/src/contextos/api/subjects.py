"""Subjects: the courses files get sorted into."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlmodel import Session, func, select

from contextos.db import get_session
from contextos.ingest.classify import normalise_semester
from contextos.ingest.pipeline import PALETTE
from contextos.models import Document, Subject, Task

router = APIRouter(prefix="/subjects", tags=["subjects"])


class SubjectIn(BaseModel):
    name: str
    code: str | None = None
    aliases: list[str] = []
    semester: str | None = None
    color: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name is required")
        return v[:60]

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, v: list[str]) -> list[str]:
        return [a.strip() for a in v if a.strip()][:20]


class SubjectOut(SubjectIn):
    id: int
    documents: int = 0


def _out(session: Session, s: Subject) -> SubjectOut:
    n = session.exec(
        select(func.count()).select_from(Document).where(Document.subject_id == s.id)
    ).one()
    return SubjectOut(id=s.id, name=s.name, code=s.code, aliases=s.aliases or [],
                      semester=s.semester, color=s.color, documents=n)


@router.get("", response_model=list[SubjectOut])
def list_subjects(session: Session = Depends(get_session)) -> list[SubjectOut]:
    return [_out(session, s) for s in session.exec(select(Subject).order_by(Subject.name))]


@router.post("", response_model=SubjectOut, status_code=201)
def create_subject(body: SubjectIn, session: Session = Depends(get_session)) -> SubjectOut:
    clash = session.exec(select(Subject).where(func.lower(Subject.name) == body.name.lower()))
    if clash.first():
        raise HTTPException(409, f"subject {body.name!r} already exists")
    count = session.exec(select(func.count()).select_from(Subject)).one()
    s = Subject(
        name=body.name, code=(body.code or "").strip() or None, aliases=body.aliases,
        semester=normalise_semester(body.semester) or (body.semester or None),
        color=body.color or PALETTE[count % len(PALETTE)],
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return _out(session, s)


@router.put("/{subject_id}", response_model=SubjectOut)
def update_subject(subject_id: int, body: SubjectIn,
                   session: Session = Depends(get_session)) -> SubjectOut:
    s = session.get(Subject, subject_id)
    if s is None:
        raise HTTPException(404, "subject not found")
    s.name = body.name
    s.code = (body.code or "").strip() or None
    s.aliases = body.aliases
    s.semester = normalise_semester(body.semester) or (body.semester or None)
    s.color = body.color or s.color
    session.add(s)
    session.commit()
    session.refresh(s)
    return _out(session, s)


@router.delete("/{subject_id}", status_code=204)
def delete_subject(subject_id: int, session: Session = Depends(get_session)) -> None:
    """Forget a subject. Its files stay where they are; they just lose the label."""
    s = session.get(Subject, subject_id)
    if s is None:
        raise HTTPException(404, "subject not found")
    for model in (Document, Task):
        for row in session.exec(select(model).where(model.subject_id == subject_id)):
            row.subject_id = None
            session.add(row)
    session.delete(s)
    session.commit()
