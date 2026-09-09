from __future__ import annotations

import math
from typing import Any


class KPICalculator:
    """
    Calculate Key Performance Indicators for water quality management.
    
    Metrics include:
    - Turbidity reduction (effectiveness)
    - Energy cost (sustainability)
    - Stability (reliability)
    - Response time
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.baseline_turbidity = 5.0  # NTU (typical baseline)
        self.cost_per_m3_flow = 0.02  # ¥/m³
        self.cost_per_kw_aeration = 0.5  # ¥/kWh
        self.effect_weights = self.config.get(
            "effect_weights",
            {"flow": 0.18, "aeration": 0.09, "chemical": 0.09},
        )

    def compute(self, action: dict[str, Any], state: dict[str, Any]) -> dict[str, float]:
        """
        Compute KPIs for a given action and state.

        Args:
            action: Action taken by the system
            state: Current state

        Returns:
            Dictionary of KPIs
        """
        current_turbidity = self._finite_value(state.get("turbidity", self.baseline_turbidity), self.baseline_turbidity)

        # Extract action parameters (with defaults)
        release_rate = self._finite_value(action.get("release_rate", 0.0), 0.0)  # m³/s
        aeration_intensity = self._finite_value(action.get("aeration_intensity", 0.0), 0.0)  # kW
        chemical_dosage = self._finite_value(action.get("chemical_dosage", 0.0), 0.0)  # kg/day

        # KPI 1: Turbidity reduction potential
        # Simplified model: more flow + more aeration = more reduction
        turbidity_reduction_ratio = (
            float(self.effect_weights.get("flow", 0.18)) * min(release_rate / 10.0, 1.0)
            + float(self.effect_weights.get("aeration", 0.09)) * min(aeration_intensity / 50.0, 1.0)
            + float(self.effect_weights.get("chemical", 0.09)) * min(chemical_dosage / 100.0, 1.0)
        )
        turbidity_reduction_ratio = min(turbidity_reduction_ratio, 0.4)  # Max 40% reduction per episode

        turbidity_reduction = current_turbidity * turbidity_reduction_ratio

        # KPI 2: Energy cost
        daily_flow_cost = release_rate * 86400 * self.cost_per_m3_flow  # Convert s to day
        daily_aeration_cost = aeration_intensity * 24 * self.cost_per_kw_aeration  # 24h/day
        daily_chemical_cost = chemical_dosage * 0.1  # Rough estimate

        energy_cost = daily_flow_cost + daily_aeration_cost + daily_chemical_cost
        manual_baseline_cost = self.config.get("manual_baseline_cost", 35000.0)
        cost_saving_ratio = max(0.0, min(1.0, 1.0 - energy_cost / manual_baseline_cost))

        # KPI 3: Stability (how consistently we can maintain reduction)
        # Based on normalized action magnitude stability.
        normalized_action_magnitude = (
            abs(release_rate) / 15.0
            + abs(aeration_intensity) / 100.0
            + abs(chemical_dosage) / 500.0
        )
        stability = 1.0 - 0.04 * normalized_action_magnitude
        stability = max(0.0, min(1.0, stability))

        # KPI 4: Response time (simplified: assume responses in 1-2 hours)
        response_time_hours = 1.0 if normalized_action_magnitude > 0.1 else 0.5

        return {
            "turbidity_reduction": float(turbidity_reduction),
            "turbidity_reduction_ratio": float(turbidity_reduction_ratio),
            "energy_cost": float(energy_cost),
            "cost_saving_ratio": float(cost_saving_ratio),
            "stability": float(stability),
            "response_time_hours": float(response_time_hours),
            "action_magnitude": float(normalized_action_magnitude),
        }

    def _finite_value(self, value: Any, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return numeric if math.isfinite(numeric) else default
