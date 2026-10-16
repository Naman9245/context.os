"""LLM providers behind one interface. See base.py for retries, cache and rate limits."""

from __future__ import annotations

from contextos.config import Settings, get_settings
from contextos.llm.base import (
    LLMError,
    LLMProvider,
    LLMUnavailable,
    TransientLLMError,
    parse_json_text,
)

__all__ = [
    "LLMError",
    "LLMProvider",
    "LLMUnavailable",
    "TransientLLMError",
    "get_llm",
    "parse_json_text",
    "set_llm",
]

_llm: LLMProvider | None = None
_built = False


def build_llm(settings: Settings) -> LLMProvider | None:
    """The configured provider, or None in heuristics-only mode (LLM_PROVIDER=none)."""
    if settings.llm_provider == "none":
        return None

    # Imported lazily: httpx lives in the `llm` extra.
    from contextos.llm.cache import LLMCache

    common = dict(
        requests_per_minute=settings.llm_requests_per_minute,
        cache=LLMCache(settings.llm_cache_dir),
        max_retries=settings.llm_max_retries,
        timeout=settings.llm_timeout_seconds,
    )
    if settings.llm_provider == "gemini":
        from contextos.llm.gemini import GeminiProvider

        return GeminiProvider(
            settings.gemini_api_key,
            settings.gemini_model,
            settings.gemini_fallback_model,
            thinking_level=settings.gemini_thinking_level,
            **common,
        )
    if settings.llm_provider == "groq":
        from contextos.llm.groq import GroqProvider

        return GroqProvider(
            settings.groq_api_key,
            settings.groq_model,
            settings.groq_fallback_model,
            **common,
        )
    raise LLMError(f"unknown LLM_PROVIDER {settings.llm_provider!r}")


def get_llm() -> LLMProvider | None:
    """Process-wide provider, so every caller shares one rate limiter."""
    global _llm, _built
    if not _built:
        _llm = build_llm(get_settings())
        _built = True
    return _llm


def set_llm(provider: LLMProvider | None) -> None:
    """Swap the provider - used by tests to inject a fake."""
    global _llm, _built
    _llm = provider
    _built = True
