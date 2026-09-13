from __future__ import annotations

from typing import Any

from .base import BaseAgent
from .checkpoint_inference import TimeSeriesCheckpointRunner


class MSCIMAgent(BaseAgent):
    """
    MSCIM diagnosis agent.
    
    Provides turbidity prediction, driver attribution,
    and uncertainty quantification.
    """

    def __init__(self, name: str = "MSCIMAgent", config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.checkpoint_path = self.config.get("checkpoint_path", "outputs/models/mscim.pt")
        self.runner = TimeSeriesCheckpointRunner(
            checkpoint_path=self.checkpoint_path,
            model_kind="mscim",
            data_path=self.config.get(
                "data_path", "outputs/intermediate/multimodal_daily_dataset.csv"
            ),
            device=self.config.get("device", "auto"),
        )

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Run MSCIM inference on current state.

        Args:
            state: Current water quality state from DataLoader

        Returns:
            Diagnosis result with predictions and attributions
        """
        try:
            return self._act_with_checkpoint(state)
        except Exception as exc:
            fallback = self._fallback_act(state)
            fallback["inference_source"] = "fallback_rules"
            fallback["checkpoint_error"] = str(exc)
            return fallback

    def _act_with_checkpoint(self, state: dict[str, Any]) -> dict[str, Any]:
        prediction = self.runner.predict(state)
        outputs = prediction.outputs
        predicted_turbidity = float(outputs.get("turbidity_pred", 0.0))
        clearness = float(outputs.get("clearness_pred", 1.0 / (1.0 + predicted_turbidity / 10.0)))
        delta_gate = float(outputs.get("delta_gate", 0.0))
        baseline = float(outputs.get("baseline_log_turbidity", 0.0))
        delta = float(outputs.get("delta_log_turbidity", 0.0))

        drivers = [
            {
                "factor": item["feature"],
                "importance": item["importance"],
                "value": prediction.feature_values.get(item["feature"], 0.0),
            }
            for item in prediction.top_features
        ]

        return {
            "model": "MSCIM",
            "checkpoint_path": self.checkpoint_path,
            "inference_source": "checkpoint",
            "prediction": {
                "turbidity": predicted_turbidity,
                "turbidity_confidence": self._confidence_from_outputs(delta_gate, delta),
                "clearness_proxy": clearness,
                "log_turbidity": float(outputs.get("log_turbidity_pred", 0.0)),
            },
            "diagnosis": {
                "primary_drivers": drivers,
                "dominant_driver": drivers[0] if drivers else None,
                "uncertainty": {
                    "epistemic": max(0.01, 0.10 * (1.0 - abs(delta_gate - 0.5) * 2.0)),
                    "aleatoric": max(0.01, min(0.20, abs(delta) * 0.5)),
                },
                "model_signals": {
                    "delta_gate": delta_gate,
                    "baseline_log_turbidity": baseline,
                    "delta_log_turbidity": delta,
                },
            },
        }

    def _fallback_act(self, state: dict[str, Any]) -> dict[str, Any]:
        # Extract key features from state
        turbidity = state.get("turbidity", 0.0)
        chlorophyll = state.get("chlorophyll_a", 0.0)
        water_temp = state.get("water_temp", 0.0)

        # Simplified MSCIM logic (in production, this would load checkpoint and run model)
        # For now, return mock predictions based on state
        predicted_turbidity = turbidity * 0.8 + 0.5  # Simplified prediction

        # Driver attribution (mock)
        rainfall_3d = state.get("rainfall_3d", 0.0)

        drivers = []
        if rainfall_3d > 36.0:
            drivers.append({"factor": "external_rainfall", "importance": 0.8, "threshold_exceeded": True})
        if chlorophyll > 5.0:
            drivers.append({"factor": "algae_growth", "importance": 0.6})
        if water_temp > 25.0:
            drivers.append({"factor": "temperature_stress", "importance": 0.4})

        return {
            "model": "MSCIM",
            "checkpoint_path": self.checkpoint_path,
            "prediction": {
                "turbidity": float(predicted_turbidity),
                "turbidity_confidence": 0.78,  # Baseline from README
                "clearness_proxy": 1.0 / (1.0 + predicted_turbidity / 10.0),
            },
            "diagnosis": {
                "primary_drivers": drivers,
                "dominant_driver": drivers[0] if drivers else None,
                "uncertainty": {
                    "epistemic": 0.05,
                    "aleatoric": 0.08,
                },
            },
        }

    def _confidence_from_outputs(self, delta_gate: float, delta: float) -> float:
        gate_confidence = 0.65 + 0.25 * abs(delta_gate - 0.5) * 2.0
        delta_penalty = min(abs(delta) * 0.15, 0.12)
        return max(0.50, min(0.95, gate_confidence - delta_penalty))

    def health(self) -> dict[str, Any]:
        """Check agent health — whether the model runs, not whether a file exists.

        Existence was the old test, and it is the reason a checkpoint that
        ``load_state_dict`` rejects still reported ``ready``: the swap on
        2026-09-08 was signed off by a signal that could not fail, while every
        request was answered by :meth:`_fallback_act`. Readiness has to mean the
        model is loaded — see :attr:`TimeSeriesCheckpointRunner.ready`, which
        loads rather than merely looking.
        """
        loaded = self.runner.ready
        return {
            "agent": self.name,
            "checkpoint": self.checkpoint_path,
            "status": "ready" if loaded else "degraded",
            "checkpoint_loaded": loaded,
            "checkpoint_error": self.runner.load_error,
        }
