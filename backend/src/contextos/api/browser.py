"""The "Khushi for Chrome" extension connects here."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from contextos.browser import EXTENSION_ORIGIN, bridge
from contextos.security import LOCAL_HOSTS, hostname

router = APIRouter(tags=["browser"])


@router.websocket("/browser/ws")
async def extension_socket(ws: WebSocket) -> None:
    # WebSockets skip the HTTP middleware, so check here: this laptop, and only our
    # extension - a website cannot fake the Origin header a browser sends.
    if hostname(ws.headers.get("host", "")) not in LOCAL_HOSTS or \
            ws.headers.get("origin") != EXTENSION_ORIGIN:
        await ws.close(code=1008)
        return
    await ws.accept()
    await bridge.serve(ws)
