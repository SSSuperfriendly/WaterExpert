from __future__ import annotations

from typing import Any


class FeedbackLoop:
    def update(self, state: dict[str, Any], action: dict[str, Any], metrics: dict[str, float]) -> dict[str, Any]:
        return {"state": state, "action": action, "metrics": metrics}
