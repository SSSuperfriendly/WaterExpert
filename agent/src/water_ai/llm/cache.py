from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ResponseCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as fh:
                    self._cache = json.load(fh)
            except Exception:
                self._cache = {}

    def get(self, prompt: str) -> Any:
        return self._cache.get(prompt)

    def set(self, prompt: str, response: Any) -> None:
        self._cache[prompt] = response
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(self._cache, fh, ensure_ascii=False, indent=2)
