"""Desktop notifications - the way Khushi taps you on the shoulder."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys

log = logging.getLogger(__name__)

APP_NAME = "Khushi"


def notifications_available() -> bool:
    if sys.platform.startswith("linux"):
        return shutil.which("notify-send") is not None
    if sys.platform == "darwin":
        return shutil.which("osascript") is not None
    try:
        import plyer  # noqa: F401 - Windows path
    except ImportError:
        return False
    return True


def notify(title: str, body: str) -> bool:
    """Show a desktop notification. Returns False (and never raises) if it can't."""
    try:
        if sys.platform.startswith("linux"):
            if not shutil.which("notify-send"):
                return False
            subprocess.run(
                ["notify-send", "--app-name", APP_NAME, "--icon", "appointment-soon",
                 title, body],
                check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        if sys.platform == "darwin":
            def q(s: str) -> str:
                return s.replace("\\", "\\\\").replace('"', '\\"')

            script = f'display notification "{q(body)}" with title "{q(title)}"'
            subprocess.run(["osascript", "-e", script], check=True, timeout=10)
            return True
        from plyer import notification  # Windows: pip install -e ".[reminders]"

        notification.notify(title=title, message=body, app_name=APP_NAME, timeout=10)
        return True
    except Exception as e:  # a notification must never take the app down
        log.warning("could not show notification: %s", e)
        return False
