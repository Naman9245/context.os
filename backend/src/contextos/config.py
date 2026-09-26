"""Settings, read from the environment and a `.env` file.

Everything has a working default so `contextos serve` runs on a fresh
machine with no configuration. API keys are only ever read from the
environment - they are never written to the database.
"""

from __future__ import annotations

from functools import lru_cache
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

    # "none" is the heuristics-only mode: nothing leaves the machine.
    llm_provider: LLMProviderName = "none"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    # Characters of a document's text sent to the LLM, never the whole file.
    llm_snippet_chars: int = 1500

    host: str = "127.0.0.1"
    port: int = 8000

    @field_validator("watch_dirs", mode="before")
    @classmethod
    def _split_dirs(cls, value: object) -> object:
        if isinstance(value, str):
            return [p.strip() for p in value.split(",") if p.strip()]
        return value

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
