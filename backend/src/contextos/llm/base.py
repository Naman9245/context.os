"""The provider interface every LLM backend implements.

Subclasses only implement `_request` (one HTTP call to one model). This base
class owns everything a free tier needs around that call:

- a rate limiter per model, so each stays under its requests-per-minute quota;
- a chain of fallback models: free tiers are per model, and Google's models
  take turns being overloaded, so a busy model is skipped at once for the next;
- retries with backoff only on the last model in the chain;
- an on-disk cache, so re-scanning a file never spends quota twice;
- JSON mode validated against a Pydantic model, with one repair retry.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Sequence
from typing import Literal, TypeVar

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
    """No model could answer. `kind` says why, so the user can be told the truth:
    "busy" (try again in a minute) or "quota" (used up for today)."""

    def __init__(self, message: str, kind: Literal["busy", "quota"] = "busy"):
        super().__init__(message)
        self.kind = kind


def model_chain(model: str, fallbacks: str | Sequence[str] | None) -> list[str]:
    """[main, *fallbacks] without blanks or repeats. Fallbacks may be "a,b,c"."""
    if isinstance(fallbacks, str):
        fallbacks = fallbacks.split(",")
    chain: list[str] = []
    for m in [model, *(fallbacks or [])]:
        m = m.strip()
        if m and m not in chain:
            chain.append(m)
    return chain


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_text(text: str) -> object:
    """Parse model output as JSON, tolerating ```json fences around it."""
    return json.loads(_FENCE.sub("", text.strip()))


class LLMProvider:
    name = "base"

    def __init__(
        self,
        model: str,
        fallbacks: str | Sequence[str] | None = None,
        *,
        requests_per_minute: int = 0,
        cache: LLMCache | None = None,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        cooldown_seconds: float = 60.0,
    ):
        self.models = model_chain(model, fallbacks)
        self.model = self.models[0]
        self.requests_per_minute = requests_per_minute
        self.cache = cache
        self.max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self.cooldown_seconds = cooldown_seconds
        self._limiters: dict[str, RateLimiter] = {}
        # model -> (clock time before which it is not worth asking, why). Saves
        # paying for a busy or exhausted model on every request.
        self._cooldown: dict[str, tuple[float, str]] = {}

    def _limiter(self, model: str) -> RateLimiter:
        if model not in self._limiters:
            self._limiters[model] = RateLimiter(self.requests_per_minute, sleep=self._sleep)
        return self._limiters[model]

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
        now = self._clock()
        cooling = {m: why for m, (until, why) in self._cooldown.items() if until > now}
        ready = [m for m in self.models if m not in cooling]
        if not ready:
            # Busy models may have recovered - better to try them than to give up.
            ready = [m for m in self.models if cooling.get(m) == "busy"]
        if not ready:
            raise LLMUnavailable(f"{', '.join(self.models)} are out of quota for now",
                                 kind="quota")
        last: LLMError | None = None
        busy = False
        for i, model in enumerate(ready):
            is_last = i == len(ready) - 1
            try:
                # A busy model is skipped at once while others remain: the next one is
                # more likely to answer than a retry is. Only the last one is retried.
                return self._with_retries(model, system, prompt, json_mode,
                                          retries=self.max_retries if is_last else 0)
            except ModelUnavailable as e:
                last = e
                wait = e.retry_after if e.retry_after is not None else 24 * 3600
                self._cooldown[model] = (self._clock() + min(wait, 24 * 3600), "quota")
            except TransientLLMError as e:
                last = e
                busy = True
                if not is_last:
                    self._cooldown[model] = (self._clock() + self.cooldown_seconds, "busy")
        raise LLMUnavailable(f"no model could answer ({', '.join(ready)}): {last}",
                             kind="busy" if busy else "quota") from last

    def _with_retries(self, model: str, system: str, prompt: str, json_mode: bool,
                      retries: int) -> str:
        for attempt in range(retries + 1):
            self._limiter(model).acquire()
            try:
                return self._request(model, system, prompt, json_mode)
            except TransientLLMError as e:
                if attempt == retries:
                    raise
                backoff = 2.0 * (2**attempt)  # 2s, 4s, 8s...
                self._sleep(min(e.retry_after or backoff, 30.0))
        raise AssertionError("unreachable")
