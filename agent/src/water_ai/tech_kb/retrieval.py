from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def cosine_similarity_matrix(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    matrix_norm = np.linalg.norm(matrix, axis=1, keepdims=True)
    vector_norm = np.linalg.norm(vector)
    denominator = np.maximum(matrix_norm.flatten() * vector_norm, 1e-12)
    return (matrix @ vector) / denominator


class TechRetrieval:
    def __init__(self, seed_path: str | Path, embedding_path: str | Path | None = None) -> None:
        self.seed_path = Path(seed_path)
        self.embedding_path = Path(embedding_path) if embedding_path is not None else None
        self.candidates = self._load_candidates()
        self.embeddings = self._load_embeddings()

    def _load_candidates(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not self.seed_path.exists():
            return items
        with self.seed_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return items

    def _load_embeddings(self) -> np.ndarray | None:
        if self.embedding_path is None or not self.embedding_path.exists():
            return None
        try:
            return np.load(self.embedding_path)
        except (OSError, ValueError):
            return None

    def retrieve(self, query_vector: np.ndarray, top_k: int = 3) -> list[dict[str, Any]]:
        if self.embeddings is None or len(self.candidates) == 0:
            return self.candidates[:top_k]
        similarity = cosine_similarity_matrix(self.embeddings, query_vector.reshape(-1))
        indices = similarity.argsort()[::-1][:top_k]
        return [self.candidates[i] for i in indices.tolist()]
