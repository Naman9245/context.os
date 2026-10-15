"""Run scans in the background, one at a time.

A scan with the LLM on can take minutes (free tiers allow ~10 requests a
minute), so the API starts it on a thread and the UI polls `status()`.
A scan requested while one is running (e.g. the folder watcher firing)
is queued as a single re-run, not stacked.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlmodel import Session

from contextos.config import get_settings
from contextos.db import get_engine
from contextos.ingest.pipeline import scan
from contextos.llm import get_llm
from contextos.models import utcnow

log = logging.getLogger(__name__)


@dataclass
class JobState:
    running: bool = False
    done: int = 0
    total: int = 0
    current: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    report: dict | None = None
    error: str | None = None


class ScanJob:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = JobState()
        self._rerun = False

    def status(self) -> dict:
        with self._lock:
            return asdict(self._state)

    def request(self, *, wait: bool = False) -> bool:
        """Start a scan. Returns False if one was already running (a re-run is queued)."""
        with self._lock:
            if self._state.running:
                self._rerun = True
                return False
            self._state = JobState(running=True, started_at=utcnow(),
                                   report=self._state.report)
        if wait:
            self._run()
        else:
            threading.Thread(target=self._run, name="contextos-scan", daemon=True).start()
        return True

    def _progress(self, done: int, total: int, current: str) -> None:
        with self._lock:
            self._state.done, self._state.total, self._state.current = done, total, current

    def _run(self) -> None:
        while True:
            report, error = None, None
            try:
                with Session(get_engine()) as session:
                    report = asdict(scan(session, get_settings(), get_llm(),
                                         progress=self._progress))
            except Exception as e:
                log.exception("scan failed")
                error = str(e)[:300]
            with self._lock:
                self._state.report = report
                self._state.error = error
                if self._rerun:
                    self._rerun = False
                    self._state.done = self._state.total = 0
                    continue
                self._state.running = False
                self._state.current = ""
                self._state.finished_at = utcnow()
                return


scan_job = ScanJob()
