from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ScenarioBase:
    name: str
    trigger: dict[str, Any]
    action_space: dict[str, Any]

    def matches(self, state: dict[str, Any]) -> bool:
        return all(state.get(k) == v for k, v in self.trigger.items())

    def propose(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"scenario": self.name, "recommended_action": self.action_space}
