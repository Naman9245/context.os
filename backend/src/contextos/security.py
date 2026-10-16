"""Who may talk to ContextOS: pages and the extension on this laptop, nobody else."""

from __future__ import annotations

from urllib.parse import urlsplit

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def hostname(value: str) -> str:
    """The host in a Host or Origin header, lower-cased, without port or brackets."""
    return (urlsplit(value if "//" in value else f"//{value}").hostname or "").lower()
