"""Carry out an approved plan, and undo it.

The two safety rules of the whole app live here:
- files are only ever *moved*, never deleted or overwritten;
- every move is written to MoveLog first, so a batch can be put back.
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from contextos.ingest.planner import avoid_collision, inside
from contextos.models import (
    ActivityEvent,
    ActivityKind,
    DocStatus,
    Document,
    MoveLog,
    utcnow,
)


@dataclass
class MoveResult:
    batch_id: str
    moved: list[int] = field(default_factory=list)
    failed: dict[int, str] = field(default_factory=dict)


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():  # shutil.move would silently overwrite on some platforms
        raise FileExistsError(f"{dst} already exists")
    shutil.move(str(src), str(dst))


def apply_plan(session: Session, document_ids: list[int], library_root: Path) -> MoveResult:
    result = MoveResult(batch_id=uuid.uuid4().hex[:12])
    taken: set[Path] = set()

    for doc_id in document_ids:
        doc = session.get(Document, doc_id)
        if doc is None:
            result.failed[doc_id] = "not found"
            continue
        if doc.status != DocStatus.planned or not doc.planned_path:
            result.failed[doc_id] = f"not ready to move (status {doc.status})"
            continue

        src = Path(doc.current_path)
        dst = Path(doc.planned_path)
        if not inside(dst, library_root):
            result.failed[doc_id] = "destination is outside the library"
            continue
        if not src.exists():
            result.failed[doc_id] = "file is no longer where it was found"
            continue

        dst = avoid_collision(dst, taken)
        try:
            _move(src, dst)
        except OSError as e:
            result.failed[doc_id] = str(e)
            continue
        taken.add(dst)

        session.add(MoveLog(batch_id=result.batch_id, document_id=doc_id,
                            from_path=str(src), to_path=str(dst)))
        doc.current_path = str(dst)
        doc.planned_path = str(dst)
        doc.status = DocStatus.organized
        doc.updated_at = utcnow()
        session.add(doc)
        session.commit()  # per file: a crash mid-batch must not lose the undo log
        result.moved.append(doc_id)

    if result.moved:
        session.add(ActivityEvent(kind=ActivityKind.files_organized, count=len(result.moved)))
        session.commit()
    return result


def undo_batch(session: Session, batch_id: str, library_root: Path) -> MoveResult:
    """Move every file in a batch back to where it was found."""
    result = MoveResult(batch_id=batch_id)
    logs = session.exec(
        select(MoveLog).where(MoveLog.batch_id == batch_id, MoveLog.undone == False)  # noqa: E712
        .order_by(MoveLog.id.desc())
    ).all()

    for log in logs:
        src, dst = Path(log.to_path), Path(log.from_path)
        doc = session.get(Document, log.document_id)
        if not src.exists():
            result.failed[log.document_id] = "file is no longer in the library"
            continue
        try:
            _move(src, dst)
        except OSError as e:
            result.failed[log.document_id] = str(e)
            continue
        log.undone = True
        session.add(log)
        if doc is not None:
            doc.current_path = str(dst)
            doc.status = DocStatus.planned
            doc.updated_at = utcnow()
            session.add(doc)
        session.commit()
        result.moved.append(log.document_id)
        _prune_empty_dirs(src.parent, library_root)

    return result


def _prune_empty_dirs(start: Path, library_root: Path) -> None:
    """Remove folders the batch created and left empty - never files, never the root."""
    root = library_root.resolve()
    d = start.resolve()
    while d != root and d.is_relative_to(root):
        try:
            d.rmdir()  # only succeeds on an empty directory
        except OSError:
            return
        d = d.parent
