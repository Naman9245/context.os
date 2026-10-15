"""Things ContextOS is allowed to do on the laptop.

This is an allowlist, not a shell: every action is a specific function with
its own checks. The chat agent (Phase 5) will call these and nothing else.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class ActionNotAllowed(Exception):
    pass


def open_path(path: Path, allowed_roots: list[Path]) -> None:
    """Open a file with the system's default app - only inside the given folders."""
    resolved = path.resolve()
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed_roots):
        raise ActionNotAllowed(f"{path} is outside the library and watched folders")
    if not resolved.is_file():
        raise FileNotFoundError(str(path))

    if sys.platform.startswith("win"):
        os.startfile(resolved)  # type: ignore[attr-defined]
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(resolved)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
