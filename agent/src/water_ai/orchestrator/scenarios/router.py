from __future__ import annotations

from typing import Any

from .s1_external_input import ScenarioExternalInput
from .s2_internal_release import ScenarioInternalRelease
from .s3_algae_bloom import ScenarioAlgaeBloom
from .s4_chronic_combo import ScenarioChronicCombo


class ScenarioRouter:
    def __init__(self) -> None:
        self.scenarios = [
            ScenarioExternalInput(),
            ScenarioInternalRelease(),
            ScenarioAlgaeBloom(),
            ScenarioChronicCombo(),
        ]

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        for scenario in self.scenarios:
            if scenario.matches(state):
                return scenario.propose(state)
        return {"scenario": "unknown", "recommended_action": {}}
