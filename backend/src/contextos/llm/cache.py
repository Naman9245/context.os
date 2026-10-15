"""On-disk cache of LLM replies, so the same question is never paid for twice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class LLMCache:
    def __init__(self, directory: Path):
        self.directory = directory

    @staticmethod
    def key(provider: str, model: str, system: str, prompt: str, json_mode: bool) -> str:
        payload = json.dumps([provider, model, system, prompt, json_mode], ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key}.txt"

    def get(self, key: str) -> str | None:
        path = self._path(key)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def put(self, key: str, text: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    def drop(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
