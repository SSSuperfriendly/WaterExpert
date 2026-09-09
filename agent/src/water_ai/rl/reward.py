from __future__ import annotations

from typing import Any


class MultiObjectiveReward:
    def compute(self, metrics: dict[str, float], weights: dict[str, float]) -> float:
        score = 0.0
        total_weight = 0.0
        for name, value in metrics.items():
            weight = float(weights.get(name, 1.0))
            score += value * weight
            total_weight += weight
        return float(score / total_weight) if total_weight > 0 else 0.0
