import json

import httpx
import pytest
from pydantic import BaseModel

from contextos.llm.base import LLMError, LLMUnavailable, parse_json_text
from contextos.llm.cache import LLMCache
from contextos.llm.gemini import GeminiProvider
from contextos.llm.groq import GroqProvider
from contextos.llm.ratelimit import RateLimiter


class Answer(BaseModel):
    word: str


def gemini_reply(text: str) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def make_gemini(handler, **kwargs) -> tuple[GeminiProvider, list[str]]:
    """A Gemini provider whose HTTP calls go to `handler`; returns the models it was asked."""
    asked: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path.split("/")[-1].split(":")[0])
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    sleeps: list[float] = []
    p = GeminiProvider("test-key", "main-model", "backup-model", client=client,
                       sleep=sleeps.append, **kwargs)
    return p, asked


def test_gemini_sends_key_in_header_not_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-goog-api-key"]
        return gemini_reply("hi")

    p, _ = make_gemini(handler)
    assert p.complete("hello") == "hi"
    assert seen["key"] == "test-key"
    assert "test-key" not in seen["url"]


def test_busy_model_is_skipped_at_once_for_the_next():
    def handler(request):
        if "main-model" in request.url.path:
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})
        return gemini_reply("from backup")

    p, asked = make_gemini(handler, max_retries=2)
    assert p.complete("hello") == "from backup"
    assert asked == ["main-model", "backup-model"]  # no 20 seconds of retrying a busy model


def test_only_the_last_model_is_retried():
    replies = iter([httpx.Response(503), httpx.Response(503), gemini_reply("finally")])
    p, asked = make_gemini(lambda r: next(replies), max_retries=2)
    assert p.complete("hello") == "finally"
    assert asked == ["main-model", "backup-model", "backup-model"]


def test_a_chain_of_fallbacks_is_tried_in_order():
    asked: list[str] = []

    def handler(request):
        model = request.url.path.split("/")[-1].split(":")[0]
        asked.append(model)
        return gemini_reply(model) if model == "third" else httpx.Response(503)

    p = GeminiProvider("k", "main", "second, third ,main,", sleep=lambda s: None,
                       client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert p.models == ["main", "second", "third"]  # blanks and repeats dropped
    assert p.complete("q") == "third"
    assert asked == ["main", "second", "third"]


def quota_429(seconds: str) -> httpx.Response:
    return httpx.Response(429, json={"error": {"code": 429, "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": seconds}]}})


def test_daily_quota_goes_straight_to_fallback_and_stays_away():
    now = [0.0]
    asked: list[str] = []

    def handler(request):
        model = request.url.path.split("/")[-1].split(":")[0]
        asked.append(model)
        return quota_429("36467s") if model == "main-model" else gemini_reply("backup")

    p = GeminiProvider("k", "main-model", "backup-model", sleep=lambda s: None,
                       clock=lambda: now[0],
                       client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert p.complete("one") == "backup"
    assert asked == ["main-model", "backup-model"]  # no pointless retries
    asked.clear()
    now[0] = 3600
    p.complete("two")
    assert asked == ["backup-model"]                 # still hours before the quota resets
    asked.clear()
    now[0] = 36500
    p.complete("three")
    assert asked[0] == "main-model"                  # quota reset: main is back


def test_short_429_is_retried_like_busy():
    replies = iter([quota_429("2s"), gemini_reply("ok")])
    asked: list[str] = []

    def handler(request):
        asked.append("only-model")
        return next(replies)

    p = GeminiProvider("k", "only-model", sleep=lambda s: None,
                       client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert p.complete("q") == "ok"
    assert asked == ["only-model", "only-model"]


def test_when_every_model_is_out_of_quota_no_requests_are_wasted():
    p, asked = make_gemini(lambda r: quota_429("50000s"))
    with pytest.raises(LLMUnavailable) as first:
        p.complete("one")
    assert first.value.kind == "quota"
    asked.clear()
    with pytest.raises(LLMUnavailable, match="out of quota") as second:
        p.complete("two")
    assert asked == [] and second.value.kind == "quota"


def test_thinking_level_is_sent_and_dropped_if_rejected():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "thinkingConfig" in body["generationConfig"]:
            return httpx.Response(400, json={"error": {"message": "thinking_level not supported"}})
        return gemini_reply("ok")

    p, _ = make_gemini(handler)
    assert p.complete("q") == "ok"
    assert bodies[0]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert "thinkingConfig" not in bodies[1]["generationConfig"]
    p.complete("again")
    assert "thinkingConfig" not in bodies[2]["generationConfig"]  # remembered


def test_all_models_busy_raises_unavailable_saying_busy():
    p, asked = make_gemini(lambda r: httpx.Response(503), max_retries=1)
    with pytest.raises(LLMUnavailable) as e:
        p.complete("hello")
    assert e.value.kind == "busy"  # "try again in a minute", not "quota used up"
    assert asked == ["main-model", "backup-model", "backup-model"]


def test_busy_models_are_tried_again_rather_than_giving_up():
    p, asked = make_gemini(lambda r: httpx.Response(503), max_retries=0)
    with pytest.raises(LLMUnavailable):
        p.complete("one")
    asked.clear()
    with pytest.raises(LLMUnavailable):
        p.complete("two")  # main is cooling down, but backup is still worth a try
    assert asked == ["backup-model"]


def test_busy_main_model_is_skipped_for_a_while():
    now = [0.0]

    def handler(request):
        if "main-model" in request.url.path:
            return httpx.Response(503)
        return gemini_reply("from backup")

    asked: list[str] = []

    def record(request):
        asked.append(request.url.path.split("/")[-1].split(":")[0])
        return handler(request)

    p = GeminiProvider("k", "main-model", "backup-model", max_retries=1, sleep=lambda s: None,
                       clock=lambda: now[0], cooldown_seconds=120,
                       client=httpx.Client(transport=httpx.MockTransport(record)))
    p.complete("one")
    assert asked == ["main-model", "backup-model"]
    asked.clear()
    p.complete("two")                      # within the cooldown: no time wasted on main
    assert asked == ["backup-model"]
    asked.clear()
    now[0] = 121
    p.complete("three")                    # cooldown over: main gets another chance
    assert asked[0] == "main-model"


def test_retired_model_goes_straight_to_fallback():
    def handler(request):
        if "main-model" in request.url.path:
            return httpx.Response(404, json={"error": {"message": "no longer available"}})
        return gemini_reply("from backup")

    p, asked = make_gemini(handler)
    assert p.complete("hello") == "from backup"
    assert asked == ["main-model", "backup-model"]


def test_bad_key_is_not_retried():
    p, asked = make_gemini(lambda r: httpx.Response(400, json={"error": "API key not valid"}))
    with pytest.raises(LLMError) as e:
        p.complete("hello")
    assert not isinstance(e.value, LLMUnavailable)
    assert asked == ["main-model"]


def test_thought_parts_are_dropped():
    reply = {"candidates": [{"content": {"parts": [
        {"text": "thinking...", "thought": True}, {"text": "answer"}]}}]}
    p, _ = make_gemini(lambda r: httpx.Response(200, json=reply))
    assert p.complete("q") == "answer"


def test_cache_means_one_request(tmp_path):
    p, asked = make_gemini(lambda r: gemini_reply("cached"), cache=LLMCache(tmp_path))
    assert p.complete("same question") == "cached"
    assert p.complete("same question") == "cached"
    assert len(asked) == 1


def test_complete_json_validates_and_repairs_once():
    replies = iter(["not json at all", '{"word": "fixed"}'])
    p, asked = make_gemini(lambda r: gemini_reply(next(replies)))
    assert p.complete_json("q", Answer) == Answer(word="fixed")
    assert len(asked) == 2


def test_complete_json_gives_up_after_one_repair():
    p, _ = make_gemini(lambda r: gemini_reply('{"wrong": 1}'))
    with pytest.raises(LLMError):
        p.complete_json("q", Answer)


def test_json_mode_and_schema_are_sent():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return gemini_reply('{"word": "x"}')

    p, _ = make_gemini(handler)
    p.complete_json("q", Answer, system="be brief")
    body = bodies[0]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    system_text = body["systemInstruction"]["parts"][0]["text"]
    assert "be brief" in system_text and '"word"' in system_text


def test_parse_json_text_strips_fences():
    assert parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}


def test_groq_json_mode():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer gk"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"word": "g"}'}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = GroqProvider("gk", "llama", client=client)
    assert p.complete_json("q", Answer).word == "g"
    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert bodies[0]["messages"][0]["role"] == "system"


def test_rate_limiter_spaces_calls_evenly():
    now = [0.0]
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    limiter = RateLimiter(30, clock=lambda: now[0], sleep=sleep)  # one every 2s
    for _ in range(3):
        limiter.acquire()
    assert slept == [2.0, 2.0]


def test_missing_key_is_a_clear_error():
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiProvider("", "m")
