from __future__ import annotations

from .base import ScenarioBase


class ScenarioAlgaeBloom(ScenarioBase):
    def __init__(self) -> None:
        super().__init__(name="algae_bloom", trigger={"chlorophyll": "high"}, action_space={"aeration": 0.4})
