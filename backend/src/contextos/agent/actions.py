"""Things ContextOS is allowed to do on the laptop.

This is an allowlist, not a shell: every action is a specific function with
its own checks, and the chat agent can call these and nothing else. All
process starts go through `_spawn`, which tests replace.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from contextos.agent.apps import App, installed_command


class ActionNotAllowed(Exception):
    pass


def _spawn(argv: list[str]) -> None:
    """Start a program detached from ContextOS, so closing one never closes the other."""
    subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, start_new_session=True)


def _open_with_system(target: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        _spawn(["open", target])
    else:
        _spawn(["xdg-open", target])


def open_path(path: Path, allowed_roots: list[Path]) -> None:
    """Open a file with the system's default app - only inside the given folders."""
    resolved = path.resolve()
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed_roots):
        raise ActionNotAllowed(f"{path} is outside the library and watched folders")
    if not resolved.is_file():
        raise FileNotFoundError(str(path))
    _open_with_system(str(resolved))


def open_url(url: str) -> None:
    """Open a web page (or a spotify: link) in the default browser / app."""
    scheme = urlsplit(url).scheme.lower()
    if scheme not in ("http", "https", "spotify"):
        raise ActionNotAllowed(f"won't open {scheme or 'that'} links")
    _open_with_system(url)


def launch_app(app: App) -> str:
    """Start an allowlisted app. Returns "app" or "web" for what was opened."""
    command = installed_command(app)
    if command:
        _spawn([command])
        return "app"
    if app.web:
        open_url(app.web)
        return "web"
    raise ActionNotAllowed(f"{app.name} doesn't seem to be installed")
