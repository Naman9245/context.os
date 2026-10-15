"""Groq over its OpenAI-compatible chat completions API."""

from __future__ import annotations

import httpx

from contextos.llm.base import (
    QUOTA_WAIT_SECONDS,
    LLMError,
    LLMProvider,
    ModelUnavailable,
    TransientLLMError,
)

API = "https://api.groq.com/openai/v1/chat/completions"
BUSY = {500, 502, 503, 504}


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: str | None = None,
        *,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
        **kwargs,
    ):
        super().__init__(model, fallback_model, **kwargs)
        if not api_key:
            raise LLMError("GROQ_API_KEY is not set")
        self._client = client or httpx.Client(timeout=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def _request(self, model: str, system: str, prompt: str, json_mode: bool) -> str:
        messages = [{"role": "user", "content": prompt}]
        if system:
            messages.insert(0, {"role": "system", "content": system})
        body: dict = {"model": model, "messages": messages, "temperature": 0.2}
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        try:
            r = self._client.post(API, headers=self._headers, json=body)
        except httpx.TransportError as e:
            raise TransientLLMError(f"network error: {e}") from e

        header = r.headers.get("retry-after", "")
        delay = float(header) if header.replace(".", "", 1).isdigit() else None
        if r.status_code == 429:
            if delay is not None and delay > QUOTA_WAIT_SECONDS:
                raise ModelUnavailable(f"{model}: quota used up", retry_after=delay)
            raise TransientLLMError(f"{model}: rate limited", retry_after=delay)
        if r.status_code in BUSY:
            raise TransientLLMError(f"{model}: busy (HTTP {r.status_code})", retry_after=delay)
        if r.status_code == 404:
            raise ModelUnavailable(f"{model}: not available to this key")
        if r.status_code != 200:
            raise LLMError(f"{model}: HTTP {r.status_code}: {r.text[:300]}")

        try:
            return r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise LLMError(f"{model}: unexpected reply shape") from e
