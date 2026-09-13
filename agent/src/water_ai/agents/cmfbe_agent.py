from __future__ import annotations

from typing import Any

from .base import BaseAgent
from .checkpoint_inference import TimeSeriesCheckpointRunner


class CMFBEAgent(BaseAgent):
    """
    CMFBE-ST-GCN mechanism-aware agent.
    
    Provides process decomposition, threshold response analysis,
    and counterfactual predictions.
    """

    def __init__(self, name: str = "CMFBEAgent", config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.checkpoint_path = self.config.get("checkpoint_path", "outputs/models/cmfbe_stgcn.pt")
        self.threshold_summary = self.config.get(
            "threshold_summary_path", "outputs/thresholds/cmfbe_threshold_summary.csv"
        )
        self.runner = TimeSeriesCheckpointRunner(
            checkpoint_path=self.checkpoint_path,
            model_kind="cmfbe",
            data_path=self.config.get(
                "data_path", "outputs/intermediate/multimodal_daily_dataset.csv"
            ),
            device=self.config.get("device", "auto"),
        )

    def act(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Run CMFBE process analysis on current state.

        Args:
            state: Current water quality state

        Returns:
            Process decomposition and threshold analysis
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

        processes = {
            "runoff_input": float(outputs.get("runoff_source", 0.0)),
            "resuspension": float(outputs.get("erosion_source", 0.0)),
            "tidal_pumping": float(outputs.get("tidal_source", 0.0)),
            "biological_growth": float(outputs.get("phytoplankton_source", 0.0)),
            "deposition": float(outputs.get("krone_deposition_sink", 0.0)),
            "flushing": float(outputs.get("flushing_sink", 0.0)),
            "purification": float(outputs.get("purification_sink", 0.0)),
        }
        source_total = float(outputs.get("source_total", 0.0))
        sink_total = float(outputs.get("sink_total", 0.0))
        physics_delta = float(outputs.get("physics_delta_log_turbidity", source_total - sink_total))
        predicted_turbidity = float(outputs.get("turbidity_pred", 0.0))

        return {
            "model": "CMFBE-ST-GCN",
            "checkpoint_path": self.checkpoint_path,
            "inference_source": "checkpoint",
            "process_decomposition": processes,
            "net_change": physics_delta,
            "thresholds": self._thresholds(),
            "threshold_breaches": self._threshold_breaches(state),
            "predictions": {
                "next_day_turbidity": predicted_turbidity,
                "physics_turbidity": float(outputs.get("physics_turbidity_pred", predicted_turbidity)),
                "clearness_proxy": float(outputs.get("clearness_pred", 0.0)),
                "next_day_turbidity_trend": "increasing" if physics_delta > 0 else "decreasing",
                "confidence": self._confidence_from_balance(source_total, sink_total),
            },
            "physics": {
                "velocity_proxy": float(outputs.get("velocity_proxy", 0.0)),
                "bed_shear_proxy": float(outputs.get("bed_shear_proxy", 0.0)),
                "source_total": source_total,
                "sink_total": sink_total,
                "fusion_ratio": float(outputs.get("fusion_ratio", 0.0)),
            },
        }

    def _fallback_act(self, state: dict[str, Any]) -> dict[str, Any]:
        # Extract features for process decomposition
        rainfall_3d = state.get("rainfall_3d", 0.0)
        rainfall_7d = state.get("rainfall_7d", 0.0)
        huangdu_flow = state.get("huangdu_flow_m3s", 0.0)
        turbidity_7d_mean = state.get("turbidity_7d_mean", 0.0)
        chlorophyll = state.get("chlorophyll_a", 0.0)

        # Empirical thresholds from README
        thresholds = self._thresholds()

        # Process decomposition (source/sink terms)
        processes = {
            "runoff_input": self._compute_runoff(rainfall_3d),
            "resuspension": self._compute_resuspension(huangdu_flow),
            "deposition": self._compute_deposition(turbidity_7d_mean),
            "biological_growth": self._compute_biological(chlorophyll),
            "flushing": self._compute_flushing(huangdu_flow),
        }

        # Net balance
        net_turbidity_change = (
            processes["runoff_input"]
            + processes["resuspension"]
            + processes["biological_growth"]
            - processes["deposition"]
            - processes["flushing"]
        )

        # Threshold responses
        threshold_breaches = self._threshold_breaches(state)

        return {
            "model": "CMFBE-ST-GCN",
            "checkpoint_path": self.checkpoint_path,
            "process_decomposition": processes,
            "net_change": float(net_turbidity_change),
            "thresholds": thresholds,
            "threshold_breaches": threshold_breaches,
            "predictions": {
                "next_day_turbidity_trend": "increasing" if net_turbidity_change > 0 else "decreasing",
                "confidence": 0.74,  # From README baseline
            },
        }

    def _thresholds(self) -> dict[str, float]:
        return {
            "rainfall_3d": 35.9,
            "rainfall_7d": 141.6,
            "flushing_potential": 3.646,
            "huangdu_flow": 22.9,
        }

    def _threshold_breaches(self, state: dict[str, Any]) -> list[dict[str, float]]:
        thresholds = self._thresholds()
        rainfall_3d = float(state.get("rainfall_3d", state.get("precipitation_3d", 0.0)) or 0.0)
        rainfall_7d = float(state.get("rainfall_7d", state.get("precipitation_7d", 0.0)) or 0.0)
        huangdu_flow = float(state.get("huangdu_flow_m3s", 0.0) or 0.0)
        flushing = float(state.get("songpu_flushing_potential", 0.0) or 0.0)

        breaches = []
        for name, value in [
            ("rainfall_3d", rainfall_3d),
            ("rainfall_7d", rainfall_7d),
            ("huangdu_flow", huangdu_flow),
            ("flushing_potential", flushing),
        ]:
            if value > thresholds[name]:
                breaches.append({"threshold": name, "value": value})
        return breaches

    def _confidence_from_balance(self, source_total: float, sink_total: float) -> float:
        total = abs(source_total) + abs(sink_total)
        if total <= 1e-6:
            return 0.68
        dominance = abs(source_total - sink_total) / total
        return max(0.55, min(0.92, 0.65 + 0.25 * dominance))

    def _compute_runoff(self, rainfall_3d: float) -> float:
        """Compute runoff contribution to turbidity."""
        # More rain → more sediment input
        if rainfall_3d < 10:
            return 0.1
        elif rainfall_3d < 36:
            return 0.3 * (rainfall_3d / 36.0)
        else:
            return min(2.0, 0.3 + 0.05 * (rainfall_3d - 36.0))

    def _compute_resuspension(self, flow: float) -> float:
        """Compute resuspension potential."""
        # Higher flow → more bottom disturbance
        return min(1.5, 0.05 * flow)

    def _compute_deposition(self, baseline_turbidity: float) -> float:
        """Compute deposition/settling rate."""
        # Higher baseline → more material to settle
        return min(1.0, 0.15 * baseline_turbidity)

    def _compute_biological(self, chlorophyll: float) -> float:
        """Compute biological (algae) contribution."""
        if chlorophyll < 5:
            return 0.0
        else:
            return min(1.0, 0.1 * (chlorophyll - 5.0))

    def _compute_flushing(self, flow: float) -> float:
        """Compute flushing/export rate."""
        # Higher flow → more material exported
        return min(2.0, 0.08 * flow)

    def health(self) -> dict[str, Any]:
        return {
            "agent": self.name,
            "checkpoint": self.checkpoint_path,
            "threshold_summary": self.threshold_summary,
            # Loaded, not merely present — see ``MSCIMAgent.health``.
            "status": "ready" if self.runner.model is not None else "degraded",
            "checkpoint_loaded": self.runner.model is not None,
            "checkpoint_error": self.runner.load_error,
        }
