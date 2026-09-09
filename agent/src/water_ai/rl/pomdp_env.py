from __future__ import annotations

from typing import Any


class POMDPEnvironment:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.state = self.reset()

    def reset(self) -> dict[str, Any]:
        self.state = {"turbidity": 0.0, "flow": 0.0, "step": 0}
        return self.state

    def step(self, action: dict[str, Any]) -> tuple[dict[str, Any], float, bool, dict[str, Any]]:
        self.state["step"] += 1
        self.state["flow"] += float(action.get("release_rate", 0.0))
        self.state["turbidity"] = max(0.0, self.state["turbidity"] - 0.1 * self.state["flow"])
        reward = -self.state["turbidity"]
        done = self.state["step"] >= int(self.config.get("horizon", 10))
        return self.state, reward, done, {}
