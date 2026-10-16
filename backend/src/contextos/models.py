"""Database tables.

One SQLite file holds everything. Paths are stored as strings; the
filesystem is the source of truth for file contents, the database only
remembers what ContextOS knows *about* each file.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class DocType(StrEnum):
    notes = "notes"
    slides = "slides"
    assignment = "assignment"
    question_paper = "question_paper"
    lab = "lab"
    syllabus = "syllabus"
    notice = "notice"
    other = "other"


class DocStatus(StrEnum):
    new = "new"  # scanned, not yet classified
    planned = "planned"  # classified, has a proposed destination
    organized = "organized"  # moved into the library
    skipped = "skipped"  # user chose to leave it where it is


class TaskSource(StrEnum):
    manual = "manual"
    chat = "chat"
    extracted = "extracted"


class TaskStatus(StrEnum):
    # Found in a document and waiting for the user: either a deadline to confirm,
    # or (due_at empty) an assignment Khushi could not find a deadline for.
    suggested = "suggested"
    todo = "todo"
    done = "done"
    # The user said "not a deadline" - kept so a rescan does not suggest it again.
    dismissed = "dismissed"


class ActivityKind(StrEnum):
    task_done = "task_done"
    session = "session"
    files_organized = "files_organized"


class Subject(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    code: str | None = None
    # Other names the subject shows up under in filenames, e.g. ["DBMS", "BCS403"].
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    semester: str | None = None
    color: str | None = None


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sha256: str = Field(index=True, unique=True)
    original_path: str
    current_path: str = Field(index=True)
    filename: str
    # Size + mtime let a rescan skip re-hashing files it has already seen.
    size_bytes: int = 0
    mtime: float = 0.0
    doc_type: DocType = DocType.other
    subject_id: int | None = Field(default=None, foreign_key="subject.id")
    title: str | None = None
    semester: str | None = None
    confidence: float = 0.0
    # How the text was read: pdf | ocr | ocr_unavailable | docx | pptx | image | none
    extraction: str | None = None
    # Who decided subject/type: "rules" or the LLM provider's name.
    classified_by: str | None = None
    text_snippet: str = ""
    planned_path: str | None = None
    error: str | None = None
    status: DocStatus = DocStatus.new
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class MoveLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    batch_id: str = Field(index=True)
    document_id: int = Field(foreign_key="document.id")
    from_path: str
    to_path: str
    moved_at: datetime = Field(default_factory=utcnow)
    undone: bool = False


class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    notes: str | None = None
    subject_id: int | None = Field(default=None, foreign_key="subject.id")
    # Local wall-clock time, not UTC: a deadline is "23:59 on the 12th" wherever you are.
    # Every other timestamp in this file is a UTC instant.
    due_at: NaiveDatetime | None = Field(default=None, index=True)
    source: TaskSource = TaskSource.manual
    source_document_id: int | None = Field(default=None, foreign_key="document.id")
    status: TaskStatus = Field(default=TaskStatus.todo, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    # Reminder offsets (days before due) already sent, so each fires once.
    reminded_days: list[int] | None = Field(default=None, sa_column=Column(JSON))


class TaskStep(SQLModel, table=True):
    """One line of an assignment's to-do list."""

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    text: str
    done: bool = False
    position: int = 0
    # Who wrote it: "you", "rules", or the LLM provider's name.
    written_by: str = "you"


class StudySession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    subject_id: int | None = Field(default=None, foreign_key="subject.id")
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    minutes: float = 0.0


class ActivityEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: ActivityKind
    ref_id: int | None = None
    count: int = 1
    at: datetime = Field(default_factory=utcnow, index=True)


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str


class ChatMessage(SQLModel, table=True):
    """One message in the conversation with Khushi."""

    id: int | None = Field(default=None, primary_key=True)
    role: str  # "user" | "khushi"
    text: str
    # Khushi's extras: actions taken, task/file ids to show as cards, suggestions.
    payload: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
