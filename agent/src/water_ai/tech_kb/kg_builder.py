from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class KnowledgeGraphBuilder:
    def __init__(self, seed_path: str | Path) -> None:
        self.seed_path = Path(seed_path)

    def build(self) -> list[dict[str, Any]]:
        triples: list[dict[str, Any]] = []
        if not self.seed_path.exists():
            return triples
        with self.seed_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    triples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return triples
