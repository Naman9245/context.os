"""The Files page: the organised library, and opening a file."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from contextos.agent.actions import ActionNotAllowed, open_path
from contextos.api.schemas import DocumentOut, documents_out
from contextos.config import get_settings
from contextos.db import get_session
from contextos.models import DocStatus, Document

router = APIRouter(prefix="/files", tags=["files"])


@router.get("", response_model=list[DocumentOut])
def list_files(session: Session = Depends(get_session)) -> list[DocumentOut]:
    docs = session.exec(
        select(Document).where(Document.status == DocStatus.organized)
        .order_by(Document.semester, Document.title)
    ).all()
    return documents_out(session, list(docs))


@router.post("/{doc_id}/open", status_code=204)
def open_file(doc_id: int, session: Session = Depends(get_session)) -> None:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    settings = get_settings()
    try:
        open_path(Path(doc.current_path), [settings.library_root, *settings.watch_dirs])
    except ActionNotAllowed as e:
        raise HTTPException(403, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(404, "the file is no longer there") from e
