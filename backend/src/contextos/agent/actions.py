"""Things ContextOS is allowed to do on the laptop.

This is an allowlist, not a shell: every action is a specific function with
its own checks, and the chat agent can call these and nothing else. All
process starts go through `_spawn`, which tests replace.

On Linux, programs are started by the user's desktop session (systemd-run
--user), not as children of ContextOS. A child inherits ContextOS's
restrictions: run from a sandboxed terminal (the Claude app's, for one) it
carries "no new privileges", and snap apps such as VS Code and Spotify then
die at once with "snap-confine ... cannot continue". Started by the session,
an app runs exactly as if its icon had been clicked, with a clean desktop
environment, and outlives ContextOS.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from contextos.agent.apps import App, installed_command

# How long to watch a fresh launch for an immediate failure (bad install,
# missing display...). Real apps that start fine are still "active" by then.
SETTLE_SECONDS = 1.0


class ActionNotAllowed(Exception):
    pass


class LaunchFailed(Exception):
    """The program started but quit straight away - it did not really open."""


class _NoSession(Exception):
    """No systemd user session to start programs in."""


def _spawn(argv: list[str]) -> None:
    """Start a program detached from ContextOS. Raises LaunchFailed if it dies at once."""
    if sys.platform.startswith("linux") and shutil.which("systemd-run"):
        try:
            return _spawn_in_session(argv)
        except _NoSession:
            pass  # e.g. WSL or a distro without systemd: start it ourselves
    subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, start_new_session=True)


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True,
                          timeout=10)


def _unit_state(unit: str) -> tuple[str, str]:
    out = _systemctl("show", unit, "-p", "ActiveState", "-p", "Result").stdout
    props = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return props.get("ActiveState", ""), props.get("Result", "")


def _why_it_failed(unit: str) -> str:
    """The program's own last words, without systemd's bookkeeping lines."""
    log = subprocess.run(["journalctl", "--user", "-u", unit, "-o", "cat", "-n", "20",
                          "--no-pager"], capture_output=True, text=True, timeout=10).stdout
    own = [line.strip() for line in log.splitlines() if line.strip() and not re.match(
        r"(Started|Stopped|Starting|Stopping) |.*(Main process exited|Failed with result)",
        line.strip())]
    return own[-1][:200] if own else "it closed straight away"


def _spawn_in_session(argv: list[str]) -> None:
    name = re.sub(r"[^A-Za-z0-9_-]", "-", Path(argv[0]).name)[:30]
    unit = f"contextos-{name}-{uuid.uuid4().hex[:8]}"
    started = subprocess.run(
        ["systemd-run", "--user", "--quiet", f"--unit={unit}",
         f"--description=Opened by ContextOS: {Path(argv[0]).name}",
         # Launchers often hand off to a child and exit; keep the unit (and the
         # app) alive until everything it started has exited.
         "-p", "ExitType=cgroup", "--", *argv],
        capture_output=True, text=True, timeout=10)
    if started.returncode != 0:
        raise _NoSession(started.stderr.strip())

    deadline = time.monotonic() + SETTLE_SECONDS
    while time.monotonic() < deadline:
        state, result = _unit_state(unit)
        if state == "failed" or (state == "inactive" and result not in ("", "success")):
            reason = _why_it_failed(unit)
            _systemctl("reset-failed", unit)  # don't leave a failed unit lying around
            raise LaunchFailed(reason)
        if state == "inactive":
            return  # handed off and done, e.g. to an app that was already open
        time.sleep(0.1)


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
    """Open a web page (or a spotify: link) in the default browser / app.

    With the "Khushi for Chrome" extension, web pages go to Khushi's own tab for
    that site instead of a new tab every time.
    """
    scheme = urlsplit(url).scheme.lower()
    if scheme not in ("http", "https", "spotify"):
        raise ActionNotAllowed(f"won't open {scheme or 'that'} links")
    if scheme in ("http", "https"):
        from contextos.browser import bridge

        if bridge.open(url):
            return
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
