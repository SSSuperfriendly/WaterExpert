from __future__ import annotations

from typing import Any


class CVaREvaluator:
    def evaluate(self, returns: list[float], alpha: float = 0.05) -> float:
        if not returns:
            return 0.0
        sorted_returns = sorted(returns)
        cutoff = max(1, int(len(sorted_returns) * alpha))
        return float(sum(sorted_returns[:cutoff]) / cutoff)
