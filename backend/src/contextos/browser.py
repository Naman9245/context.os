"""The "Khushi for Chrome" extension (browser-extension/): Khushi's own tabs.

Opening a link through the system always makes Chrome open a new tab, and
Chrome lets no outside program pick a tab. The extension can: it keeps one
Khushi tab per site and reuses it, so "open YouTube" then "search carryminati
on YouTube" happen in the same tab.

The extension holds a WebSocket open to ContextOS; `bridge.open()` asks it to
open a link and waits briefly for the answer. Without the extension (or if it
does not answer) the caller opens the link the normal way - nothing breaks.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import uuid
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

# Fixed by the "key" in browser-extension/manifest.json: only this extension is accepted.
EXTENSION_ID = "nhmecidkacagicpgoncmkbokbainkjik"
EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}"
PING_SECONDS = 20.0  # also keeps the extension's background worker awake
OPEN_TIMEOUT = 3.0
# Picking the first result may wait up to ~10 s for a results page to load.
FIRST_RESULT_TIMEOUT = 12.0

_TWO_PART_SUFFIXES = {"co.in", "co.uk", "ac.in", "edu.in", "org.in", "gov.in", "net.in",
                      "res.in", "com.au", "co.jp"}


def site_of(url: str) -> str:
    """'https://en.m.wikipedia.org/wiki/X' -> 'wikipedia.org'. Matches siteOf() in the extension."""
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return ""
    if host == "youtu.be":
        return "youtube.com"
    parts = host.split(".")
    keep = 3 if ".".join(parts[-2:]) in _TWO_PART_SUFFIXES else 2
    return ".".join(parts[-keep:])


class BrowserBridge:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ws = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: dict[str, asyncio.Future] = {}

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._ws is not None

    async def serve(self, ws) -> None:
        """Run one (already accepted) extension connection until it closes."""
        with self._lock:
            self._ws, self._loop = ws, asyncio.get_running_loop()
        pinger = asyncio.create_task(self._ping(ws))
        try:
            while True:
                try:
                    msg = json.loads(await ws.receive_text())
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "result":
                    fut = self._pending.pop(str(msg.get("id")), None)
                    if fut is not None and not fut.done():
                        fut.set_result(msg)
        except Exception:  # the extension went away (Chrome closed, reloaded...)
            pass
        finally:
            pinger.cancel()
            with self._lock:
                if self._ws is ws:
                    self._ws, self._loop = None, None

    async def _ping(self, ws) -> None:
        with contextlib.suppress(Exception):
            while True:
                await asyncio.sleep(PING_SECONDS)
                await ws.send_text(json.dumps({"type": "ping"}))

    async def _ask(self, ws, message: dict, timeout: float) -> dict:
        req_id = uuid.uuid4().hex
        fut = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        try:
            await ws.send_text(json.dumps({**message, "id": req_id}))
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(req_id, None)

    def _request(self, message: dict, timeout: float | None = None) -> dict | None:
        """Send a command and wait for the extension's answer; None if it can't answer."""
        with self._lock:
            ws, loop = self._ws, self._loop
        if ws is None or loop is None:
            return None
        try:
            if asyncio.get_running_loop() is loop:
                return None  # called on the server's own loop: can't wait here
        except RuntimeError:
            pass  # a worker thread, as expected
        timeout = OPEN_TIMEOUT if timeout is None else timeout
        try:
            return asyncio.run_coroutine_threadsafe(
                self._ask(ws, message, timeout), loop).result(timeout + 1)
        except Exception as e:
            log.info("extension did not answer %s: %s", message.get("type"), e)
            return None

    def open(self, url: str) -> bool:
        """Open `url` in Khushi's tab. False when the extension can't (not installed,
        not connected, no answer) - the caller then opens the link the normal way."""
        result = self._request({"type": "open", "url": url, "site": site_of(url)})
        return bool(result and result.get("ok"))

    def open_first(self, site: str) -> dict | None:
        """Open the first result on Khushi's results page for `site` ("play it").

        {"ok": True, "title", "url"} when it worked, {"ok": False, "error"} when the
        extension answered but couldn't, None when there is no extension to ask.
        """
        return self._request({"type": "open_first", "site": site}, FIRST_RESULT_TIMEOUT)


bridge = BrowserBridge()
