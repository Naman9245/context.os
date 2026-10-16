"""Settings, read from the environment and a `.env` file.

Everything has a working default so `contextos serve` runs on a fresh
machine with no configuration. API keys are only ever read from the
environment - they are never written to the database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LLMProviderName = Literal["none", "gemini", "groq"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Where ContextOS keeps its own state (database, LLM cache).
    data_dir: Path = Path.home() / ".contextos"
    # Where organised files end up: LIBRARY_ROOT/<Semester>/<Subject>/<Type>/.
    library_root: Path = Path.home() / "ContextOS"
    # Folders scanned for new files. Comma-separated in the environment.
    watch_dirs: Annotated[list[Path], NoDecode] = Field(
        default_factory=lambda: [Path.home() / "Downloads"]
    )

    # Watch WATCH_DIRS and scan automatically when a new file lands.
    watch_enabled: bool = True
    # How deep to look inside each watched folder (0 = only the folder itself).
    scan_max_depth: int = 3
    # How to read ambiguous numeric dates like 04/05/2026 found in documents.
    date_order: Literal["DMY", "MDY"] = "DMY"

    # Khushi reminds you this many days before a deadline. Comma-separated.
    reminder_days: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [5, 3])
    reminders_enabled: bool = True
    reminder_check_minutes: int = 15

    # "none" is the heuristics-only mode: nothing leaves the machine.
    llm_provider: LLMProviderName = "none"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    # Tried in order when the main model is busy or out of quota (comma-separated).
    # Free-tier quotas are per model, so each one adds a day's worth of requests.
    gemini_fallback_model: str = "gemini-3.5-flash-lite,gemini-flash-lite-latest"
    # How hard Gemini thinks before answering: minimal | low | medium | high, or empty for
    # the model's default. Sorting files needs little, and "minimal" is about twice as fast.
    gemini_thinking_level: str = "minimal"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_fallback_model: str = "llama-3.1-8b-instant"
    # Characters of a document's text sent to the LLM, never the whole file.
    llm_snippet_chars: int = 1500
    # Free tiers allow roughly 10-30 requests a minute; stay under it.
    llm_requests_per_minute: int = 10
    # Retries per model on "busy" errors before moving to the fallback model.
    llm_max_retries: int = 2
    llm_timeout_seconds: float = 60.0

    host: str = "127.0.0.1"
    port: int = 8000

    @field_validator("watch_dirs", mode="before")
    @classmethod
    def _split_dirs(cls, value: object) -> object:
        if isinstance(value, str):
            return [p.strip() for p in value.split(",") if p.strip()]
        return value

    @field_validator("reminder_days", mode="before")
    @classmethod
    def _split_days(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(d) for d in value.split(",") if d.strip()]
        return value

    @field_validator("reminder_days", mode="after")
    @classmethod
    def _sort_days(cls, value: list[int]) -> list[int]:
        return sorted({d for d in value if d >= 0}, reverse=True)

    @field_validator("data_dir", "library_root", mode="after")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser()

    @field_validator("watch_dirs", mode="after")
    @classmethod
    def _expand_all(cls, value: list[Path]) -> list[Path]:
        return [p.expanduser() for p in value]

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'contextos.db'}"

    @property
    def llm_cache_dir(self) -> Path:
        return self.data_dir / "llm_cache"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(settings: Settings | None) -> None:
    """Swap the settings - used by tests so nothing touches the real home folder."""
    global _settings
    _settings = settings
