"""The provider interface every LLM backend implements.

Subclasses only implement `_request` (one HTTP call to one model). This base
class owns everything a free tier needs around that call:

- a rate limiter, so we stay under the requests-per-minute quota;
- retries with backoff when the model says it is busy (429/5xx);
- a fallback model when the main one stays busy or has been retired;
- an on-disk cache, so re-scanning a file never spends quota twice;
- JSON mode validated against a Pydantic model, with one repair retry.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from contextos.llm.cache import LLMCache
from contextos.llm.ratelimit import RateLimiter

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """A request failed in a way retrying will not fix (bad key, bad request...)."""


class TransientLLMError(LLMError):
    """The model is busy or rate-limited - worth retrying, or trying the fallback."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ModelUnavailable(LLMError):
    """This model cannot answer for a long while - retired (404) or out of quota (a
    free tier's daily limit). Go to the fallback, and leave this model alone until
    `retry_after` seconds have passed."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


# A 429 asking us to wait longer than this is a used-up quota, not a burst limit.
QUOTA_WAIT_SECONDS = 30.0


class LLMUnavailable(LLMError):
    """Every model stayed busy through all retries."""


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_text(text: str) -> object:
    """Parse model output as JSON, tolerating ```json fences around it."""
    return json.loads(_FENCE.sub("", text.strip()))


class LLMProvider:
    name = "base"

    def __init__(
        self,
        model: str,
        fallback_model: str | None = None,
        *,
        limiter: RateLimiter | None = None,
        cache: LLMCache | None = None,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        cooldown_seconds: float = 120.0,
    ):
        self.model = model
        self.fallback_model = fallback_model if fallback_model != model else None
        self.limiter = limiter or RateLimiter(requests_per_minute=0)
        self.cache = cache
        self.max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self.cooldown_seconds = cooldown_seconds
        # model -> clock time before which it is not worth asking. Saves paying for
        # retries on every request while a model is busy or out of quota.
        self._cooldown_until: dict[str, float] = {}

    # -- subclass hook -----------------------------------------------------

    def _request(self, model: str, system: str, prompt: str, json_mode: bool) -> str:
        """Send one request to one model and return the text of the reply.

        Raise TransientLLMError for busy/rate-limit/network errors and LLMError
        for anything else.
        """
        raise NotImplementedError

    # -- public API --------------------------------------------------------

    def complete(self, prompt: str, *, system: str = "", json_mode: bool = False) -> str:
        key = None
        if self.cache is not None:
            key = self.cache.key(self.name, self.model, system, prompt, json_mode)
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        text = self._with_fallback(system, prompt, json_mode)

        if self.cache is not None and key is not None:
            self.cache.put(key, text)
        return text

    def complete_json(self, prompt: str, schema: type[T], *, system: str = "") -> T:
        """Ask for JSON matching `schema`. One repair attempt if the reply is invalid."""
        instructions = (
            f"{system}\n\nRespond with a single JSON object only, no prose. "
            f"It must validate against this JSON Schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        ).strip()

        text = self.complete(prompt, system=instructions, json_mode=True)
        try:
            return schema.model_validate(parse_json_text(text))
        except (ValueError, ValidationError) as first_error:
            if self.cache is not None:
                self.cache.drop(self.cache.key(self.name, self.model, instructions, prompt, True))
            repair = (
                f"{prompt}\n\nYour previous reply was not valid:\n{text[:2000]}\n"
                f"Error: {str(first_error)[:500]}\nReply again with corrected JSON only."
            )
            text = self.complete(repair, system=instructions, json_mode=True)
            try:
                return schema.model_validate(parse_json_text(text))
            except (ValueError, ValidationError) as e:
                raise LLMError(f"model did not return valid JSON: {e}") from e

    # -- retry / fallback ----------------------------------------------------

    def _with_fallback(self, system: str, prompt: str, json_mode: bool) -> str:
        models = [self.model] + ([self.fallback_model] if self.fallback_model else [])
        now = self._clock()
        ready = [m for m in models if self._cooldown_until.get(m, 0.0) <= now]
        if not ready:
            raise LLMUnavailable(f"{', '.join(models)} are out of quota or busy - try later")
        last: LLMError | None = None
        for model in ready:
            try:
                return self._with_retries(model, system, prompt, json_mode)
            except ModelUnavailable as e:
                last = e
                wait = e.retry_after if e.retry_after is not None else 24 * 3600
                self._cooldown_until[model] = self._clock() + min(wait, 24 * 3600)
            except TransientLLMError as e:
                last = e
                # Only worth skipping a busy model when there is another one to use.
                if model == self.model and self.fallback_model:
                    self._cooldown_until[model] = self._clock() + self.cooldown_seconds
        raise LLMUnavailable(f"no model could answer ({', '.join(ready)}): {last}") from last

    def _with_retries(self, model: str, system: str, prompt: str, json_mode: bool) -> str:
        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()
            try:
                return self._request(model, system, prompt, json_mode)
            except TransientLLMError as e:
                if attempt == self.max_retries:
                    raise
                backoff = 2.0 * (2**attempt)  # 2s, 4s, 8s...
                self._sleep(min(e.retry_after or backoff, 30.0))
        raise AssertionError("unreachable")
