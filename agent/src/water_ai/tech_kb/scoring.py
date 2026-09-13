from __future__ import annotations


class ApplicabilityScorer:
    def score(self, features: dict[str, float], weights: dict[str, float]) -> float:
        total = 0.0
        weight_sum = 0.0
        for key, value in features.items():
            weight = float(weights.get(key, 1.0))
            total += value * weight
            weight_sum += weight
        return float(total / weight_sum) if weight_sum > 0 else 0.0
