"""The apps and websites Khushi knows how to open, and how to search the web.

This is the allowlist: Khushi can only launch an app listed here. Anything
not installed falls back to its web version when it has one.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, quote_plus


@dataclass(frozen=True)
class App:
    key: str
    name: str
    aliases: tuple[str, ...]
    # Executables to try, in order. Windows names end in .exe so they never match
    # a Linux program (plain `calc` there is a console calculator with no window).
    commands: tuple[str, ...]
    web: str | None = None     # used when the app is not installed


APPS = [
    App("spotify", "Spotify", ("spotify",), ("spotify",), "https://open.spotify.com"),
    App("discord", "Discord", ("discord",), ("discord",), "https://discord.com/app"),
    App("chrome", "Google Chrome", ("chrome", "google chrome", "browser", "the browser"),
        ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome.exe")),
    App("firefox", "Firefox", ("firefox", "mozilla"), ("firefox", "firefox.exe")),
    App("vscode", "VS Code", ("vs code", "vscode", "visual studio code", "code editor"),
        ("code",), "https://vscode.dev"),
    App("files", "Files", ("files", "file manager", "nautilus", "file explorer", "explorer"),
        ("nautilus", "dolphin", "thunar", "nemo", "explorer.exe")),
    App("calculator", "Calculator", ("calculator", "calc"),
        ("gnome-calculator", "kcalc", "galculator", "calc.exe")),
    App("terminal", "Terminal", ("terminal", "windows terminal"),
        ("gnome-terminal", "konsole", "xfce4-terminal", "x-terminal-emulator", "wt.exe")),
    App("telegram", "Telegram", ("telegram",), ("telegram-desktop", "telegram"),
        "https://web.telegram.org"),
    App("whatsapp", "WhatsApp", ("whatsapp", "whats app"), (), "https://web.whatsapp.com"),
    App("zoom", "Zoom", ("zoom",), ("zoom",), "https://app.zoom.us/wc"),
    App("slack", "Slack", ("slack",), ("slack",), "https://app.slack.com"),
]

SITES = {
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "wikipedia": "https://www.wikipedia.org",
    "wiki": "https://www.wikipedia.org",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "mail": "https://mail.google.com",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "google classroom": "https://classroom.google.com",
    "classroom": "https://classroom.google.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "calendar": "https://calendar.google.com",
    "google calendar": "https://calendar.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "linkedin": "https://www.linkedin.com",
    "instagram": "https://www.instagram.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.in",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "leetcode": "https://leetcode.com",
    "geeksforgeeks": "https://www.geeksforgeeks.org",
    "gfg": "https://www.geeksforgeeks.org",
    "notion": "https://www.notion.so",
    "canva": "https://www.canva.com",
}

ENGINES = {
    "google": ("Google", lambda q: f"https://www.google.com/search?q={quote_plus(q)}"),
    # Special:Search jumps straight to the article when the title matches.
    "wikipedia": ("Wikipedia",
                  lambda q: f"https://en.wikipedia.org/wiki/Special:Search?search={quote_plus(q)}"),
    "youtube": ("YouTube",
                lambda q: f"https://www.youtube.com/results?search_query={quote_plus(q)}"),
    "spotify": ("Spotify", lambda q: f"https://open.spotify.com/search/{quote(q)}"),
    "maps": ("Google Maps", lambda q: f"https://www.google.com/maps/search/{quote_plus(q)}"),
    "github": ("GitHub", lambda q: f"https://github.com/search?q={quote_plus(q)}"),
}
ENGINE_ALIASES = {
    "google": "google", "wikipedia": "wikipedia", "wiki": "wikipedia", "youtube": "youtube",
    "yt": "youtube", "spotify": "spotify", "maps": "maps", "google maps": "maps",
    "github": "github",
}


def find_app(name: str) -> App | None:
    key = name.strip().lower()
    for app in APPS:
        if key == app.key or key in app.aliases:
            return app
    return None


def installed_command(app: App) -> str | None:
    for cmd in app.commands:
        path = shutil.which(cmd)
        if not path and cmd.endswith(".exe"):
            path = _app_path(cmd)
        if path:
            return path
    return None


# Where Windows installers register their programs. Chrome and Firefox install
# outside PATH, so this is the only way to find them there.
APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"


def _app_path(exe: str) -> str | None:
    """Where Windows' App Paths registry says `exe` is - per-user installs first."""
    try:
        import winreg
    except ImportError:  # not Windows
        return None
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            value = winreg.QueryValue(hive, rf"{APP_PATHS}\{exe}")
        except OSError:
            continue
        path = os.path.expandvars(value.strip('"'))  # some installers quote it
        # A missing file was left behind by an uninstall. Store apps point into the
        # locked WindowsApps folder; they start through their alias on PATH instead.
        if os.path.isfile(path) and "windowsapps" not in (p.lower() for p in Path(path).parts):
            return path
    return None


def find_site(name: str) -> str | None:
    name = name.strip().lower()
    if name in SITES:
        return SITES[name]
    # "geeksforgeeks.org", "moodle.mycollege.edu" - anything that looks like a domain.
    if re.fullmatch(r"(https?://)?[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?", name):
        return name if name.startswith("http") else f"https://{name}"
    return None


def search_url(engine: str, query: str) -> tuple[str, str]:
    """(label, url) for searching `query` on `engine` (default Google)."""
    label, build = ENGINES[ENGINE_ALIASES.get(engine.lower(), "google")]
    return label, build(query)
