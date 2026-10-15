"""Watch the download folders and trigger a scan when a new file lands.

Browsers write a download under a temporary name (.crdownload, .part) and
rename it when it finishes, and some write the final name and keep
appending. Either way a burst of events arrives, so we wait for a few
quiet seconds before scanning.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from contextos.ingest.scanner import is_candidate

log = logging.getLogger(__name__)


class FolderWatcher:
    def __init__(self, folders: list[Path], on_change: Callable[[], object],
                 debounce_seconds: float = 3.0):
        self.folders = [f for f in folders if f.is_dir()]
        self.on_change = on_change
        self.debounce_seconds = debounce_seconds
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._observer = None

    def _poke(self, path: str) -> None:
        if not is_candidate(Path(path)):
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_seconds, self.on_change)
            self._timer.daemon = True
            self._timer.start()

    def start(self) -> bool:
        if not self.folders:
            return False
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    watcher._poke(event.src_path)

            def on_modified(self, event):
                if not event.is_directory:
                    watcher._poke(event.src_path)

            def on_moved(self, event):
                if not event.is_directory:
                    watcher._poke(event.dest_path)

        observer = Observer()
        for folder in self.folders:
            observer.schedule(Handler(), str(folder), recursive=False)
        observer.daemon = True
        observer.start()
        self._observer = observer
        log.info("watching %s", ", ".join(map(str, self.folders)))
        return True

    @property
    def running(self) -> bool:
        return self._observer is not None

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
