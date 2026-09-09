from __future__ import annotations

from typing import Any


class SafeSACTrainer:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.gamma = float(self.config.get("gamma", 0.99))
        self.safe_lambda = float(self.config.get("safe_lambda", 0.1))

    def train(self, env: Any, episodes: int = 1) -> dict[str, Any]:
        history: list[float] = []
        for _ in range(episodes):
            state = env.reset()
            total_reward = 0.0
            done = False
            while not done:
                action = {"release_rate": 0.0}
                state, reward, done, _ = env.step(action)
                total_reward += reward
            history.append(total_reward)
        return {"episodes": episodes, "total_reward": sum(history), "history": history}
