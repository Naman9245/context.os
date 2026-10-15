"""The Organize page: scan, review the plan, approve, undo."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, func, select

from contextos.api.schemas import DocumentOut, documents_out
from contextos.config import get_settings
from contextos.db import get_session
from contextos.ingest.classify import normalise_semester
from contextos.ingest.jobs import scan_job
from contextos.ingest.mover import apply_plan, undo_batch
from contextos.ingest.pipeline import get_or_create_subject, replan
from contextos.models import DocStatus, DocType, Document, MoveLog, utcnow

router = APIRouter(prefix="/organize", tags=["organize"])


class ScanStatus(BaseModel):
    running: bool
    done: int
    total: int
    current: str
    started_at: datetime | None
    finished_at: datetime | None
    report: dict | None
    error: str | None
    pending: int


class Ids(BaseModel):
    document_ids: list[int]


class MoveResultOut(BaseModel):
    batch_id: str
    moved: list[int]
    failed: dict[int, str]


class Batch(BaseModel):
    batch_id: str
    count: int
    moved_at: datetime
    undone: bool


class DocumentEdit(BaseModel):
    subject: str | None = None  # a subject name; "" clears it; a new name creates it
    doc_type: DocType | None = None
    title: str | None = None
    semester: str | None = None  # "" clears it


def _pending(session: Session) -> int:
    return session.exec(
        select(func.count()).select_from(Document).where(Document.status == DocStatus.planned)
    ).one()


def _status(session: Session) -> ScanStatus:
    return ScanStatus(**scan_job.status(), pending=_pending(session))


@router.get("/status", response_model=ScanStatus)
def status(session: Session = Depends(get_session)) -> ScanStatus:
    return _status(session)


@router.post("/scan", response_model=ScanStatus)
def start_scan(wait: bool = False, session: Session = Depends(get_session)) -> ScanStatus:
    """Start a scan in the background (`wait=true` runs it inline - used by tests)."""
    scan_job.request(wait=wait)
    session.expire_all()
    return _status(session)


@router.get("/plan", response_model=list[DocumentOut])
def plan(status: DocStatus = DocStatus.planned,
         session: Session = Depends(get_session)) -> list[DocumentOut]:
    docs = session.exec(
        select(Document).where(Document.status == status).order_by(Document.updated_at.desc())
    ).all()
    return documents_out(session, list(docs))


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
def edit_document(doc_id: int, edit: DocumentEdit,
                  session: Session = Depends(get_session)) -> DocumentOut:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    if doc.status == DocStatus.organized:
        raise HTTPException(409, "already organised - undo the move first")

    if edit.subject is not None:
        doc.subject_id = get_or_create_subject(session, edit.subject).id \
            if edit.subject.strip() else None
    if edit.doc_type is not None:
        doc.doc_type = edit.doc_type
    if edit.title is not None and edit.title.strip():
        doc.title = edit.title.strip()[:120]
    if edit.semester is not None:
        raw = edit.semester.strip()[:30]
        doc.semester = normalise_semester(raw) or raw or None
    doc.classified_by = "you"
    doc.confidence = 1.0
    doc.updated_at = utcnow()
    replan(session, doc, get_settings().library_root)
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return documents_out(session, [doc])[0]


@router.post("/apply", response_model=MoveResultOut)
def apply(ids: Ids, session: Session = Depends(get_session)) -> MoveResultOut:
    result = apply_plan(session, ids.document_ids, get_settings().library_root)
    return MoveResultOut(**result.__dict__)


@router.post("/skip")
def skip(ids: Ids, session: Session = Depends(get_session)) -> dict:
    return {"updated": _set_status(session, ids.document_ids, DocStatus.planned,
                                   DocStatus.skipped)}


@router.post("/unskip")
def unskip(ids: Ids, session: Session = Depends(get_session)) -> dict:
    return {"updated": _set_status(session, ids.document_ids, DocStatus.skipped,
                                   DocStatus.planned)}


def _set_status(session: Session, ids: list[int], from_: DocStatus, to: DocStatus) -> int:
    n = 0
    for doc in session.exec(select(Document).where(Document.id.in_(ids))).all():
        if doc.status == from_:
            doc.status = to
            doc.updated_at = utcnow()
            if to == DocStatus.planned:
                replan(session, doc, get_settings().library_root)
            session.add(doc)
            n += 1
    session.commit()
    return n


@router.get("/batches", response_model=list[Batch])
def batches(session: Session = Depends(get_session)) -> list[Batch]:
    rows = session.exec(
        select(MoveLog.batch_id, func.count(), func.min(MoveLog.moved_at),
               func.min(MoveLog.undone))
        .group_by(MoveLog.batch_id)
        .order_by(func.min(MoveLog.moved_at).desc())
        .limit(10)
    ).all()
    return [Batch(batch_id=b, count=c, moved_at=t, undone=bool(u)) for b, c, t, u in rows]


@router.post("/undo/{batch_id}", response_model=MoveResultOut)
def undo(batch_id: str, session: Session = Depends(get_session)) -> MoveResultOut:
    result = undo_batch(session, batch_id, get_settings().library_root)
    if not result.moved and not result.failed:
        raise HTTPException(404, "nothing to undo in that batch")
    return MoveResultOut(**result.__dict__)
