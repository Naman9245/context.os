"""scan -> extract -> classify -> plan, for every new file in the watched folders.

The output is a dry-run plan: each new file becomes a Document with status
`planned` and a `planned_path`. Nothing on disk changes until the user
approves the plan (mover.apply_plan).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

from sqlmodel import Session, func, select

from contextos.config import Settings
from contextos.ingest.classify import SubjectRef, classify
from contextos.ingest.extract import extract
from contextos.ingest.planner import avoid_collision, target_path
from contextos.ingest.scanner import FoundFile, sha256_file, walk
from contextos.llm import LLMProvider
from contextos.models import (
    DocStatus,
    Document,
    Subject,
    Task,
    TaskSource,
    TaskStatus,
    utcnow,
)

log = logging.getLogger(__name__)

PALETTE = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#a855f7", "#14b8a6",
           "#f97316", "#84cc16", "#ec4899"]

Progress = Callable[[int, int, str], None]
_COPY_MARK = re.compile(r"\(\d+\)|\bcopy\b", re.I)


def _copy_rank(f: FoundFile) -> tuple[int, int, str]:
    """Sort key putting originals first: "a(2).pdf" before its copy "a(2) (1).pdf"."""
    return (len(_COPY_MARK.findall(f.path.stem)), len(f.path.name), str(f.path))


@dataclass
class ScanReport:
    found: int = 0
    new: int = 0
    unchanged: int = 0
    duplicates: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    used_llm: int = 0
    llm_errors: int = 0
    deadlines: int = 0


def subject_refs(session: Session) -> list[SubjectRef]:
    return [
        SubjectRef(id=s.id, name=s.name, code=s.code, aliases=tuple(s.aliases or ()),
                   semester=s.semester)
        for s in session.exec(select(Subject).order_by(Subject.name)).all()
    ]


def get_or_create_subject(session: Session, name: str, semester: str | None = None) -> Subject:
    key = name.strip().lower()
    for s in session.exec(select(Subject)).all():
        if s.name.lower() == key or (s.code and s.code.lower() == key) or \
                key in (a.lower() for a in s.aliases or ()):
            return s
    count = session.exec(select(func.count()).select_from(Subject)).one()
    subject = Subject(name=name.strip()[:60], semester=semester,
                      color=PALETTE[count % len(PALETTE)])
    session.add(subject)
    session.flush()
    return subject


def _learn_semester(session: Session, subject: Subject, semester: str, library_root: Path,
                    taken: set[Path]) -> None:
    """A subject with no semester takes the first one a file states, and files already
    planned for it without a semester follow - so they do not land in "General"."""
    subject.semester = semester
    session.add(subject)
    stragglers = session.exec(select(Document).where(
        Document.subject_id == subject.id, Document.semester == None,  # noqa: E711
        Document.status == DocStatus.planned)).all()
    for doc in stragglers:
        if doc.planned_path:
            taken.discard(Path(doc.planned_path))
        doc.semester = semester
        replan(session, doc, library_root, taken)
        session.add(doc)


def planned_paths(session: Session, exclude_id: int | None = None) -> set[Path]:
    rows = session.exec(
        select(Document.id, Document.planned_path).where(Document.status == DocStatus.planned)
    ).all()
    return {Path(p) for i, p in rows if p and i != exclude_id}


def replan(session: Session, doc: Document, library_root: Path,
           taken: set[Path] | None = None) -> None:
    """(Re)compute doc.planned_path from its current subject/type/title/semester."""
    subject = session.get(Subject, doc.subject_id) if doc.subject_id else None
    path = target_path(
        library_root,
        semester=doc.semester,
        subject=subject.name if subject else None,
        doc_type=doc.doc_type,
        title=doc.title,
        suffix=Path(doc.filename).suffix,
        fallback_title=Path(doc.filename).stem,
    )
    if taken is None:
        taken = planned_paths(session, exclude_id=doc.id)
    final = avoid_collision(path, taken)
    taken.add(final)
    doc.planned_path = str(final)


def _process_new(
    session: Session, f: FoundFile, sha: str, settings: Settings, llm: LLMProvider | None,
    today: date, taken: set[Path], report: ScanReport, reuse: Document | None,
) -> None:
    extracted = extract(f.path)
    result = classify(
        f.path.name, extracted, subject_refs(session),
        llm=llm, today=today, date_order=settings.date_order,
        snippet_chars=settings.llm_snippet_chars,
    )
    if result.classified_by != "rules":
        report.used_llm += 1
    if result.llm_error:
        report.llm_errors += 1

    subject = get_or_create_subject(session, result.subject, result.semester) \
        if result.subject else None
    if subject is not None and subject.semester is None and result.semester:
        _learn_semester(session, subject, result.semester, settings.library_root, taken)
    doc = reuse or Document(sha256=sha, original_path=str(f.path), current_path=str(f.path),
                            filename=f.path.name)
    doc.sha256 = sha
    doc.size_bytes, doc.mtime = f.size, f.mtime
    doc.doc_type = result.doc_type
    doc.subject_id = subject.id if subject else None
    doc.title = result.title
    doc.semester = result.semester or (subject.semester if subject else None)
    doc.confidence = result.confidence
    doc.classified_by = result.classified_by
    doc.extraction = extracted.method
    doc.text_snippet = extracted.text[:500]
    doc.error = extracted.error or result.llm_error
    doc.status = DocStatus.planned
    doc.updated_at = utcnow()
    session.add(doc)
    session.flush()
    replan(session, doc, settings.library_root, taken)

    # Deadlines are only suggestions - the user accepts them in Tasks.
    for d in result.deadlines:
        due_at = datetime.combine(d.due, time(23, 59))
        exists = session.exec(select(Task).where(
            Task.source_document_id == doc.id, Task.due_at == due_at)).first()
        if exists:
            continue
        session.add(Task(
            title=d.title, notes=d.line, subject_id=doc.subject_id, due_at=due_at,
            source=TaskSource.extracted, source_document_id=doc.id,
            status=TaskStatus.suggested,
        ))
        report.deadlines += 1


def scan(
    session: Session,
    settings: Settings,
    llm: LLMProvider | None,
    *,
    today: date | None = None,
    progress: Progress | None = None,
) -> ScanReport:
    today = today or date.today()
    report = ScanReport()
    progress = progress or (lambda done, total, current: None)

    files = list(walk(settings.watch_dirs, exclude=[settings.library_root],
                      max_depth=settings.scan_max_depth))
    report.found = len(files)

    # Originals before their copies, so "notes.pdf" is kept and "notes (1).pdf" is the duplicate.
    files.sort(key=_copy_rank)
    by_path = {d.current_path: d for d in session.exec(select(Document)).all()}
    todo = []
    for f in files:
        known = by_path.get(str(f.path))
        if known and known.size_bytes == f.size and known.mtime == f.mtime:
            report.unchanged += 1
        else:
            todo.append(f)

    taken = planned_paths(session)
    for i, f in enumerate(todo):
        progress(i, len(todo), f.path.name)
        try:
            sha = sha256_file(f.path)
        except OSError as e:
            report.errors.append({"path": str(f.path), "error": str(e)})
            continue

        same_content = session.exec(select(Document).where(Document.sha256 == sha)).first()
        if same_content is not None:
            if same_content.current_path == str(f.path):
                # Touched but unchanged: just remember the new mtime.
                same_content.size_bytes, same_content.mtime = f.size, f.mtime
                session.add(same_content)
                session.commit()
                report.unchanged += 1
            elif Path(same_content.current_path).exists():
                report.duplicates.append(
                    {"path": str(f.path), "same_as": same_content.current_path})
            else:
                # Moved outside ContextOS: follow it, keep what we knew about it.
                same_content.current_path = str(f.path)
                same_content.size_bytes, same_content.mtime = f.size, f.mtime
                if same_content.status == DocStatus.organized:
                    same_content.status = DocStatus.planned
                    replan(session, same_content, settings.library_root, taken)
                session.add(same_content)
                session.commit()
            continue

        # A file at a known path whose content changed is re-read in place.
        reuse = by_path.get(str(f.path))
        try:
            _process_new(session, f, sha, settings, llm, today, taken, report, reuse)
            session.commit()
            report.new += 1
        except Exception as e:  # one bad file must not stop the scan
            log.exception("failed to process %s", f.path)
            session.rollback()
            report.errors.append({"path": str(f.path), "error": str(e)[:300]})

    progress(len(todo), len(todo), "")
    return report
