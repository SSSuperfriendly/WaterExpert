from __future__ import annotations

from .base import ScenarioBase


class ScenarioChronicCombo(ScenarioBase):
    def __init__(self) -> None:
        super().__init__(name="chronic_combo", trigger={"baseline_turbidity": "elevated"}, action_space={"release_rate": 0.2, "aeration": 0.2})
