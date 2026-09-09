from __future__ import annotations

from typing import Any

from .base import BaseAgent


class SafetyAgent(BaseAgent):
    def __init__(self, name: str = "SafetyAgent", config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.constraints = self.config.get(
            "constraints",
            {
                "max_release": 15.0,
                "max_aeration": 100.0,
                "max_chemical": 500.0,
                "min_flow": 0.0,
            },
        )

    def act(self, safety_input: dict[str, Any]) -> dict[str, Any]:
        """Screen actions against safety constraints."""
        proposed_action = safety_input.get("proposed_action")
        if proposed_action is None:
            proposed_action = safety_input
        safe_action = proposed_action.copy()

        max_release = float(self.constraints.get("max_release", 15.0))
        max_aeration = float(self.constraints.get("max_aeration", 100.0))
        max_chemical = float(self.constraints.get("max_chemical", 500.0))
        
        violations = []
        
        if "release_rate" in safe_action and float(safe_action["release_rate"]) > max_release:
            violations.append("release_rate exceeded")
            safe_action["release_rate"] = max_release
        
        if "aeration_intensity" in safe_action and float(safe_action["aeration_intensity"]) > max_aeration:
            violations.append("aeration exceeded")
            safe_action["aeration_intensity"] = max_aeration
        
        if "chemical_dosage" in safe_action and float(safe_action["chemical_dosage"]) > max_chemical:
            violations.append("chemical dosage exceeded")
            safe_action["chemical_dosage"] = max_chemical
        
        for key in ["release_rate", "aeration_intensity", "chemical_dosage"]:
            if key in safe_action:
                safe_action[key] = max(0.0, float(safe_action[key]))
        
        return {
            "safe_action": safe_action,
            "safety_passed": len(violations) == 0,
            "violations": violations,
        }

    def health(self) -> dict[str, Any]:
        return {"agent": self.name, "constraints": self.constraints, "status": "ready"}
