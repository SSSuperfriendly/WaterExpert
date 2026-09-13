from __future__ import annotations


class RobustnessEvaluator:
    def evaluate(self, baseline: dict[str, float], perturbed: dict[str, float]) -> dict[str, float]:
        return {k: abs(baseline.get(k, 0.0) - perturbed.get(k, 0.0)) for k in set(baseline) | set(perturbed)}
