"""Find candidate files in the watched folders.

Pure filesystem walking - no database. The pipeline decides what is new.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".pptx", ".jpg", ".jpeg", ".png"}
SKIP_DIRS = {"node_modules", "__pycache__", "venv", ".venv", "site-packages"}
MAX_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class FoundFile:
    path: Path
    size: int
    mtime: float


def is_candidate(path: Path) -> bool:
    # Hidden files and Office lock files (~$x.docx) are never documents. Partial
    # downloads (.crdownload, .part) fall out because their suffix is unsupported.
    if path.name.startswith((".", "~$")):
        return False
    return path.suffix.lower() in SUPPORTED


def walk(roots: list[Path], *, exclude: list[Path], max_depth: int) -> Iterator[FoundFile]:
    """Yield supported files under `roots`, never descending into `exclude`.

    `exclude` is the library itself: when it sits inside Downloads, the files
    we already organised must not come back as "new".
    """
    excluded = [e.resolve() for e in exclude]
    seen: set[Path] = set()

    for root in roots:
        root = root.resolve()
        if not root.is_dir() or any(root.is_relative_to(e) for e in excluded):
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath)
            depth = len(here.parts) - base_depth
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".")
                and d not in SKIP_DIRS
                and depth < max_depth
                and not any((here / d).resolve().is_relative_to(e) for e in excluded)
            ]
            for name in filenames:
                path = here / name
                if not is_candidate(path) or path in seen:
                    continue
                try:
                    st = path.stat()
                except OSError:
                    continue
                if not path.is_file() or st.st_size == 0 or st.st_size > MAX_BYTES:
                    continue
                seen.add(path)
                yield FoundFile(path=path, size=st.st_size, mtime=st.st_mtime)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
