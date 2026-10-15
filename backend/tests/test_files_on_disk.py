"""Scanner, extractor, planner and mover - the parts that touch real files."""

from pathlib import Path

import pytest
from sqlmodel import select

from contextos.ingest import extract as extract_mod
from contextos.ingest.extract import extract
from contextos.ingest.mover import apply_plan, undo_batch
from contextos.ingest.ocr import ocr_available
from contextos.ingest.planner import avoid_collision, safe_component, target_path
from contextos.ingest.scanner import walk
from contextos.models import ActivityEvent, DocStatus, DocType, Document, MoveLog
from tests.makefiles import make_docx, make_pdf, make_pptx, make_scanned_pdf

# -- scanner -------------------------------------------------------------------


def test_scanner_finds_supported_files_and_skips_the_rest(tmp_path):
    inbox = tmp_path / "in"
    make_pdf(inbox / "a.pdf", "hello")
    make_pdf(inbox / "sub" / "b.pdf", "hello")
    (inbox / "movie.mp4").write_bytes(b"x")
    (inbox / "c.pdf.crdownload").write_bytes(b"x")  # still downloading
    (inbox / "~$lock.docx").write_bytes(b"x")       # Office lock file
    (inbox / "empty.pdf").write_bytes(b"")
    make_pdf(inbox / ".hidden" / "d.pdf", "x")
    make_pdf(inbox / "node_modules" / "e.pdf", "x")

    names = sorted(f.path.name for f in walk([inbox], exclude=[], max_depth=3))
    assert names == ["a.pdf", "b.pdf"]


def test_scanner_never_looks_inside_the_library(tmp_path):
    inbox = tmp_path / "Downloads"
    library = inbox / "ContextOS"
    make_pdf(inbox / "new.pdf", "x")
    make_pdf(library / "Sem 5" / "old.pdf", "x")
    assert [f.path.name for f in walk([inbox], exclude=[library], max_depth=5)] == ["new.pdf"]


def test_scanner_depth_limit(tmp_path):
    make_pdf(tmp_path / "top.pdf", "x")
    make_pdf(tmp_path / "a" / "b" / "deep.pdf", "x")
    assert [f.path.name for f in walk([tmp_path], exclude=[], max_depth=1)] == ["top.pdf"]


# -- extract ---------------------------------------------------------------------


def test_extract_pdf_text_and_metadata_title(tmp_path):
    p = make_pdf(tmp_path / "x.pdf", "Operating Systems\nModule 1: Introduction to processes",
                 title="OS Notes")
    out = extract(p)
    assert out.method == "pdf"
    assert "Module 1" in out.text
    assert out.meta_title == "OS Notes"


def test_extract_docx_and_pptx(tmp_path):
    d = extract(make_docx(tmp_path / "a.docx", "Assignment 3\nDue date: 5 Nov 2026"))
    assert d.method == "docx" and "Due date" in d.text
    s = extract(make_pptx(tmp_path / "b.pptx", "Normalisation", "1NF, 2NF, 3NF"))
    assert s.method == "pptx" and "3NF" in s.text


def test_scanned_pdf_without_tesseract_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod.ocr, "ocr_available", lambda: False)
    out = extract(make_pdf(tmp_path / "scan.pdf", ""))
    assert out.method == "ocr_unavailable"


@pytest.mark.skipif(not ocr_available(), reason="tesseract is not installed")
def test_scanned_pdf_is_read_with_ocr(tmp_path):
    p = make_scanned_pdf(tmp_path / "IMG_20261014_scan.pdf",
                         "Operating Systems (BCS303)\nLab Record - Experiment 4")
    out = extract(p)
    assert out.method == "ocr"
    assert "Lab Record" in out.text and "BCS303" in out.text


def test_corrupt_file_does_not_raise(tmp_path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"%PDF-1.4 this is not really a pdf")
    out = extract(p)
    assert out.text == "" and out.error


# -- planner ---------------------------------------------------------------------


def test_target_path_layout(tmp_path):
    p = target_path(tmp_path, semester="Sem 5", subject="DBMS", doc_type=DocType.assignment,
                    title="Assignment 2", suffix=".PDF", fallback_title="x")
    assert p == tmp_path / "Sem 5" / "DBMS" / "Assignments" / "Assignment 2.pdf"


def test_target_path_defaults(tmp_path):
    p = target_path(tmp_path, semester=None, subject=None, doc_type=DocType.notice,
                    title=None, suffix=".pdf", fallback_title="circular_12")
    assert p == tmp_path / "General" / "Unsorted" / "Notices" / "circular_12.pdf"


@pytest.mark.parametrize("evil", ["../../etc", "a/b", "..", "C:\\Windows", "CON", "  ..  "])
def test_unsafe_names_cannot_escape_the_library(tmp_path, evil):
    p = target_path(tmp_path, semester=evil, subject=evil, doc_type=DocType.notes,
                    title=evil, suffix=".pdf", fallback_title="f")
    assert p.resolve().is_relative_to(tmp_path.resolve())
    assert "/" not in safe_component(evil, "x") and "\\" not in safe_component(evil, "x")


def test_collisions_get_numbered(tmp_path):
    existing = make_pdf(tmp_path / "Notes.pdf", "x")
    planned = tmp_path / "Notes (2).pdf"
    assert avoid_collision(existing, {planned}) == tmp_path / "Notes (3).pdf"


# -- mover -----------------------------------------------------------------------


def _planned_doc(session, src: Path, dst: Path) -> Document:
    doc = Document(sha256=src.name, original_path=str(src), current_path=str(src),
                   filename=src.name, planned_path=str(dst), status=DocStatus.planned)
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def test_apply_then_undo_round_trip(session, tmp_path):
    inbox, library = tmp_path / "in", tmp_path / "lib"
    a = make_pdf(inbox / "a.pdf", "a")
    b = make_pdf(inbox / "b.pdf", "b")
    da = _planned_doc(session, a, library / "Sem 5" / "DBMS" / "Notes" / "A.pdf")
    db_ = _planned_doc(session, b, library / "Sem 5" / "DBMS" / "Notes" / "B.pdf")

    result = apply_plan(session, [da.id, db_.id], library)
    assert result.moved == [da.id, db_.id] and not result.failed
    assert not a.exists() and (library / "Sem 5" / "DBMS" / "Notes" / "A.pdf").exists()
    assert session.get(Document, da.id).status == DocStatus.organized
    assert session.exec(select(ActivityEvent)).one().count == 2

    undone = undo_batch(session, result.batch_id, library)
    assert sorted(undone.moved) == sorted([da.id, db_.id])
    assert a.exists() and b.exists()
    assert session.get(Document, da.id).status == DocStatus.planned
    assert not (library / "Sem 5").exists()  # empty folders cleaned up
    assert all(log.undone for log in session.exec(select(MoveLog)))


def test_never_overwrites_an_existing_file(session, tmp_path):
    library = tmp_path / "lib"
    src = make_pdf(tmp_path / "in" / "new.pdf", "new")
    dst = make_pdf(library / "Notes.pdf", "already here")
    doc = _planned_doc(session, src, dst)

    result = apply_plan(session, [doc.id], library)
    assert result.moved == [doc.id]
    assert (library / "Notes (2).pdf").exists()
    assert extract(dst).text == "already here"


def test_refuses_destinations_outside_the_library(session, tmp_path):
    src = make_pdf(tmp_path / "in" / "x.pdf", "x")
    doc = _planned_doc(session, src, tmp_path / "elsewhere" / "x.pdf")
    result = apply_plan(session, [doc.id], tmp_path / "lib")
    assert doc.id in result.failed and src.exists()


def test_missing_source_is_reported_not_crashed(session, tmp_path):
    doc = _planned_doc(session, tmp_path / "gone.pdf", tmp_path / "lib" / "gone.pdf")
    assert "no longer" in apply_plan(session, [doc.id], tmp_path / "lib").failed[doc.id]
