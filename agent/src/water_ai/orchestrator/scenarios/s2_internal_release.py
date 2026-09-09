from __future__ import annotations

from .base import ScenarioBase


class ScenarioInternalRelease(ScenarioBase):
    def __init__(self) -> None:
        super().__init__(name="internal_release", trigger={"sediment_release": "high"}, action_space={"release_rate": 0.3})
