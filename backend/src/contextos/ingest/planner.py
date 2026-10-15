"""Decide where a file should live: LIBRARY_ROOT/<Semester>/<Subject>/<Type>/<Title>.ext

Only computes paths. Nothing here touches files - mover.py does that, and
only after the user approves the plan.
"""

from __future__ import annotations

import re
from pathlib import Path

from contextos.models import DocType

TYPE_FOLDERS = {
    DocType.notes: "Notes",
    DocType.slides: "Slides",
    DocType.assignment: "Assignments",
    DocType.question_paper: "Question Papers",
    DocType.lab: "Lab",
    DocType.syllabus: "Syllabus",
    DocType.notice: "Notices",
    DocType.other: "Other",
}
NO_SEMESTER = "General"
NO_SUBJECT = "Unsorted"

# Characters Windows/macOS/Linux disallow or that would change the path.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
             *(f"lpt{i}" for i in range(1, 10))}


def safe_component(text: str | None, fallback: str, max_len: int = 80) -> str:
    """A single path segment: no separators, no '..', no trailing dots or spaces."""
    clean = _UNSAFE.sub(" ", text or "")
    clean = re.sub(r"\s+", " ", clean).strip(" .")
    if not clean or clean.lower() in _RESERVED:
        return fallback
    return clean[:max_len].rstrip(" .")


def target_path(
    library_root: Path,
    *,
    semester: str | None,
    subject: str | None,
    doc_type: DocType,
    title: str | None,
    suffix: str,
    fallback_title: str,
) -> Path:
    folder = (
        library_root
        / safe_component(semester, NO_SEMESTER)
        / safe_component(subject, NO_SUBJECT)
        / TYPE_FOLDERS[doc_type]
    )
    name = safe_component(title, safe_component(fallback_title, "Untitled"), max_len=120)
    return folder / f"{name}{suffix.lower()}"


def avoid_collision(path: Path, taken: set[Path]) -> Path:
    """`path`, or `Name (2).pdf`, `Name (3).pdf`... if it exists or is already planned."""
    candidate = path
    n = 2
    while candidate in taken or candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


def inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())
