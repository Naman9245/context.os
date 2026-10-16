"""The built React app (frontend/dist) that `contextos serve` hands out."""

from __future__ import annotations

import hashlib
from pathlib import Path

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def build_id() -> str | None:
    """Changes whenever the frontend is rebuilt, so open pages can offer a reload.

    index.html names the hashed JS/CSS bundles, so its hash changes with them.
    """
    try:
        return hashlib.sha256((FRONTEND_DIST / "index.html").read_bytes()).hexdigest()[:12]
    except OSError:
        return None
