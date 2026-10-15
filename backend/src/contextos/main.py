"""FastAPI application.

In development the React app runs on Vite's dev server and proxies `/api`
here. In production `npm run build` writes `frontend/dist`, and this app
serves it, so a single `contextos serve` starts everything.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from contextos import __version__
from contextos.api import router as api_router
from contextos.config import get_settings
from contextos.db import init_db

log = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _start_reminders(settings) -> object | None:
    from datetime import datetime

    from sqlmodel import Session

    from contextos.agent.notify import notify
    from contextos.db import get_engine
    from contextos.tasks.reminders import ReminderLoop, run_reminders

    def check() -> None:
        with Session(get_engine()) as session:
            sent = run_reminders(session, now=datetime.now(), offsets=settings.reminder_days,
                                 send=notify)
        for title in sent:
            log.info("reminded: %s", title)

    loop = ReminderLoop(check, every_seconds=settings.reminder_check_minutes * 60)
    loop.start()
    return loop


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    from sqlmodel import Session

    from contextos.db import get_engine
    from contextos.tasks.service import ensure_assignment_tasks

    with Session(get_engine()) as session:
        ensure_assignment_tasks(session)  # assignments scanned before tasks existed
    app.state.watcher = None
    settings = get_settings()
    app.state.reminders = _start_reminders(settings) if settings.reminders_enabled else None
    if settings.watch_enabled:
        try:
            from contextos.ingest.jobs import scan_job
            from contextos.ingest.watcher import FolderWatcher

            watcher = FolderWatcher(settings.watch_dirs, scan_job.request)
            if watcher.start():
                app.state.watcher = watcher
        except ImportError:
            log.warning("watchdog not installed - folder watching is off "
                        '(pip install -e ".[ingest]")')
    yield
    if app.state.watcher is not None:
        app.state.watcher.stop()
    if app.state.reminders is not None:
        app.state.reminders.stop()


def _hostname(value: str) -> str:
    return (urlsplit(value if "//" in value else f"//{value}").hostname or "").lower()


def create_app() -> FastAPI:
    app = FastAPI(title="ContextOS", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        """This API moves files and opens apps, so only this machine's pages may call it.

        - Host check: blocks DNS-rebinding (a website resolving its name to 127.0.0.1).
        - Origin check: blocks other websites' pages from POSTing to localhost.
        """
        if _hostname(request.headers.get("host", "")) not in LOCAL_HOSTS:
            return JSONResponse({"detail": "ContextOS only answers on localhost"}, 403)
        origin = request.headers.get("origin")
        if origin and _hostname(origin) not in LOCAL_HOSTS:
            return JSONResponse({"detail": "cross-site request refused"}, 403)
        return await call_next(request)

    app.include_router(api_router, prefix="/api")

    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            # Client-side routes (/tasks, /organize, ...) all load index.html.
            candidate = (FRONTEND_DIST / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(FRONTEND_DIST):
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
