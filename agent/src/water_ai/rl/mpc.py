from __future__ import annotations

from typing import Any


class MPCController:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def plan(self, state: dict[str, Any], horizon: int = 5) -> dict[str, Any]:
        return {"planned_actions": [{"release_rate": 0.1 * (i + 1)} for i in range(horizon)]}
