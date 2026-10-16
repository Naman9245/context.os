"""Google Gemini over its REST API (no SDK)."""

from __future__ import annotations

import httpx

from contextos.llm.base import (
    QUOTA_WAIT_SECONDS,
    LLMError,
    LLMProvider,
    ModelUnavailable,
    TransientLLMError,
)

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BUSY = {500, 502, 503, 504}


def retry_delay(r: httpx.Response) -> float | None:
    """Seconds Google asks us to wait, from Retry-After or the error's RetryInfo."""
    header = r.headers.get("retry-after", "")
    if header.isdigit():
        return float(header)
    try:
        details = r.json()["error"]["details"]
    except (ValueError, KeyError, TypeError):
        return None
    for d in details:
        if str(d.get("@type", "")).endswith("RetryInfo"):
            value = str(d.get("retryDelay", ""))
            try:
                return float(value.rstrip("s"))
            except ValueError:
                return None
    return None


def _human(seconds: float) -> str:
    return f"{seconds / 3600:.0f}h" if seconds >= 3600 else f"{seconds / 60:.0f} min"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        fallbacks: str | list[str] | None = None,
        *,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
        thinking_level: str | None = "minimal",
        **kwargs,
    ):
        super().__init__(model, fallbacks, **kwargs)
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self._client = client or httpx.Client(timeout=timeout)
        self._headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        # Sorting a file needs no deep reasoning; less thinking is ~2x faster.
        self.thinking_level = thinking_level or None
        self._no_thinking: set[str] = set()  # models that rejected the setting

    def _body(self, model: str, system: str, prompt: str, json_mode: bool) -> dict:
        config: dict = {"temperature": 0.2}
        if json_mode:
            config["responseMimeType"] = "application/json"
        if self.thinking_level and model not in self._no_thinking:
            config["thinkingConfig"] = {"thinkingLevel": self.thinking_level}
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body

    def _request(self, model: str, system: str, prompt: str, json_mode: bool) -> str:
        body = self._body(model, system, prompt, json_mode)
        try:
            r = self._client.post(API.format(model=model), headers=self._headers, json=body)
            if r.status_code == 400 and "thinking" in r.text.lower() and \
                    "thinkingConfig" in body["generationConfig"]:
                # Older models do not take thinkingLevel: remember, and ask again without it.
                self._no_thinking.add(model)
                body = self._body(model, system, prompt, json_mode)
                r = self._client.post(API.format(model=model), headers=self._headers, json=body)
        except httpx.TransportError as e:
            raise TransientLLMError(f"network error: {e}") from e

        if r.status_code == 429:
            delay = retry_delay(r)
            if delay is not None and delay > QUOTA_WAIT_SECONDS:
                raise ModelUnavailable(
                    f"{model}: free-tier quota used up, resets in {_human(delay)}",
                    retry_after=delay)
            raise TransientLLMError(f"{model}: rate limited", retry_after=delay)
        if r.status_code in BUSY:
            raise TransientLLMError(f"{model}: busy (HTTP {r.status_code})",
                                    retry_after=retry_delay(r))
        if r.status_code == 404:
            raise ModelUnavailable(f"{model}: not available to this key")
        if r.status_code != 200:
            # Never echo the request (it carries the key); the error body is safe.
            raise LLMError(f"{model}: HTTP {r.status_code}: {r.text[:300]}")

        data = r.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as e:
            reason = data.get("promptFeedback", {}).get("blockReason") or "no candidates"
            raise LLMError(f"{model}: empty reply ({reason})") from e
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
