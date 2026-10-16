"""The "Khushi for Chrome" bridge: Khushi's own tabs, and who may connect."""

import json
import threading
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

from contextos import browser
from contextos.agent import actions
from contextos.browser import EXTENSION_ORIGIN, bridge, site_of

# The test client invents a "testserver" host for WebSockets unless given a full URL.
WS = "ws://127.0.0.1:8000/api/browser/ws"

CASES = json.loads((Path(__file__).parents[2] / "browser-extension" / "site-cases.json")
                   .read_text())


@pytest.mark.parametrize("url, site", CASES)
def test_site_of_matches_the_extension(url, site):
    assert site_of(url) == site


def test_manifest_key_gives_the_id_contextos_trusts():
    import base64
    import hashlib

    manifest = json.loads((Path(__file__).parents[2] / "browser-extension" / "manifest.json")
                          .read_text())
    der = base64.b64decode(manifest["key"])
    ext_id = "".join("abcdefghijklmnop"[int(c, 16)]
                     for c in hashlib.sha256(der).hexdigest()[:32])
    assert ext_id == browser.EXTENSION_ID


@pytest.mark.parametrize("origin", ["https://evil.example", "http://localhost:8000",
                                    "chrome-extension://someotherextensionidxxxxxxxxxxx", None])
def test_only_khushis_extension_may_connect(client, origin):
    headers = {"origin": origin} if origin else {}
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(WS, headers=headers) as ws:
            ws.receive_text()
    assert e.value.code == 1008
    assert not bridge.connected


def test_a_foreign_host_is_refused_even_with_the_right_origin(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("ws://evil.example/api/browser/ws",
                                      headers={"origin": EXTENSION_ORIGIN}) as ws:
            ws.receive_text()
    assert e.value.code == 1008


def _open_in_thread(url):
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("ok", bridge.open(url)))
    t.start()
    return t, result


def test_links_go_to_khushis_tab_through_the_extension(client, monkeypatch):
    opened_normally = []
    monkeypatch.setattr(actions, "_open_with_system", opened_normally.append)
    with client.websocket_connect(WS,
                                  headers={"origin": EXTENSION_ORIGIN}) as ws:
        ws.send_text(json.dumps({"type": "hello", "version": "0.1.0"}))
        assert client.get("/api/health").json()["browser_extension"] is True

        url = "https://www.youtube.com/results?search_query=carryminati"
        t = threading.Thread(target=actions.open_url, args=(url,))
        t.start()
        msg = json.loads(ws.receive_text())
        assert (msg["type"], msg["url"], msg["site"]) == ("open", url, "youtube.com")
        ws.send_text(json.dumps({"type": "result", "id": msg["id"], "ok": True,
                                 "reused": True}))
        t.join(5)
    assert opened_normally == []  # the extension handled it - no new tab
    assert not bridge.connected   # and the bridge noticed it left


def test_a_silent_extension_falls_back_to_a_normal_tab(client, monkeypatch):
    monkeypatch.setattr(browser, "OPEN_TIMEOUT", 0.2)
    opened_normally = []
    monkeypatch.setattr(actions, "_open_with_system", opened_normally.append)
    with client.websocket_connect(WS, headers={"origin": EXTENSION_ORIGIN}):
        actions.open_url("https://www.google.com/search?q=x")  # nobody answers
    assert opened_normally == ["https://www.google.com/search?q=x"]


def test_without_the_extension_links_open_normally(monkeypatch):
    opened_normally = []
    monkeypatch.setattr(actions, "_open_with_system", opened_normally.append)
    actions.open_url("https://www.youtube.com")
    assert opened_normally == ["https://www.youtube.com"]


def test_a_refusal_from_the_extension_falls_back(client, monkeypatch):
    opened_normally = []
    monkeypatch.setattr(actions, "_open_with_system", opened_normally.append)
    with client.websocket_connect(WS, headers={"origin": EXTENSION_ORIGIN}) as ws:
        t, result = _open_in_thread("https://en.wikipedia.org/wiki/X")
        msg = json.loads(ws.receive_text())
        ws.send_text(json.dumps({"type": "result", "id": msg["id"], "ok": False,
                                 "error": "tabs API failed"}))
        t.join(5)
    assert result == {"ok": False}


def test_open_first_round_trip(client):
    with client.websocket_connect(WS, headers={"origin": EXTENSION_ORIGIN}) as ws:
        result = {}
        t = threading.Thread(
            target=lambda: result.update(bridge.open_first("youtube.com") or {}))
        t.start()
        msg = json.loads(ws.receive_text())
        assert (msg["type"], msg["site"]) == ("open_first", "youtube.com")
        ws.send_text(json.dumps({"type": "result", "id": msg["id"], "ok": True,
                                 "title": "First video", "url": "https://youtu.be/abc"}))
        t.join(5)
    assert result["ok"] is True and result["title"] == "First video"


def test_open_first_without_the_extension_is_none():
    assert bridge.open_first("youtube.com") is None
