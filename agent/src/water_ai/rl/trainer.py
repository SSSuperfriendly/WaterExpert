from __future__ import annotations

from typing import Any

from .pomdp_env import POMDPEnvironment
from .safe_sac import SafeSACTrainer


class RLTrainer:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.env = POMDPEnvironment(self.config.get("env", {}))
        self.algorithm = SafeSACTrainer(self.config.get("algorithm", {}))

    def train(self, episodes: int = 1) -> dict[str, Any]:
        return self.algorithm.train(self.env, episodes)
