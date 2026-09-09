from __future__ import annotations

from .base import ScenarioBase


class ScenarioExternalInput(ScenarioBase):
    def __init__(self) -> None:
        super().__init__(name="external_input", trigger={"rainfall": "high"}, action_space={"release_rate": 0.5})
