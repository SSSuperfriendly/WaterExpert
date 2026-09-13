from __future__ import annotations

import math
from typing import Any

from .base import BaseAgent
from .checkpoint_inference import TimeSeriesCheckpointRunner

#: Graph feature name -> the keys ``state`` may carry it under.
#:
#: The threshold graph names a feature by what was measured; ``state`` names it
#: by whatever the caller had to hand. The two vocabularies have differed since
#: before either side could see the other — the platform calls it
#: ``precipitation_3d``, this agent's own callers call it ``rainfall_3d`` — so
#: the translation is written down rather than derived. Fuzzy matching would not
#: do: nothing distinguishes ``songpu_flow`` from ``huangdu_flow`` by spelling,
#: and a threshold compared against the wrong column reports a breach that is
#: not there.
STATE_ALIASES: dict[str, tuple[str, ...]] = {
    "precipitation_3d": ("precipitation_3d", "rainfall_3d"),
    "precipitation_7d": ("precipitation_7d", "rainfall_7d"),
    "huangdu_flow_m3s_abs": ("huangdu_flow_m3s_abs", "huangdu_flow_m3s", "huangdu_flow"),
    "songpu_flow_m3s_abs": ("songpu_flow_m3s_abs", "songpu_flow_m3s", "songpu_flow"),
    "songpu_flushing_potential": ("songpu_flushing_potential", "flushing_potential"),
    "songpu_resuspension_potential": (
        "songpu_resuspension_potential",
        "resuspension_potential",
    ),
}

#: Where the thresholds came from. Reported on every result, because a level
#: with no provenance is a number a reader has no way to check.
THRESHOLD_SOURCE_GRAPH = "knowledge_graph"
THRESHOLD_SOURCE_NONE = "unavailable"


def _number(value: Any) -> float | None:
    """A finite float, or ``None``. Never a coerced string, never a raise.

    ``nan`` and both infinities are excluded: a threshold of ``inf`` is never
    exceeded and one of ``nan`` never compares, so either would silently turn
    the screening off while looking like it ran.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _state_value(state: dict[str, Any], feature: str) -> float | None:
    """The measured value for a graph feature, under any of its known names."""
    for key in STATE_ALIASES.get(feature, (feature,)):
        if key in state:
            number = _number(state[key])
            if number is not None:
                return number
    return None


class CMFBEAgent(BaseAgent):
    """
    CMFBE-ST-GCN mechanism-aware agent.
    
    Provides process decomposition, threshold response analysis,
    and counterfactual predictions.
    """

    def __init__(self, name: str = "CMFBEAgent", config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.checkpoint_path = self.config.get("checkpoint_path", "outputs/models/cmfbe_stgcn.pt")
        # No ``threshold_summary_path`` any more; the levels arrive with each
        # request. ``_threshold_table`` says why.
        self.runner = TimeSeriesCheckpointRunner(
            checkpoint_path=self.checkpoint_path,
            model_kind="cmfbe",
            data_path=self.config.get(
                "data_path", "outputs/intermediate/multimodal_daily_dataset.csv"
            ),
            device=self.config.get("device", "auto"),
        )

    def act(
        self,
        state: dict[str, Any],
        knowledge_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run CMFBE process analysis on current state.

        Args:
            state: Current water quality state
            knowledge_context: Graph evidence the platform retrieved for this
                request. Kept as a second argument and never merged into
                ``state``: the checkpoint runner indexes ``state`` by feature
                name, and an unexpected key there is a much worse failure than
                an extra argument here.

        Returns:
            Process decomposition and threshold analysis
        """
        try:
            return self._act_with_checkpoint(state, knowledge_context)
        except Exception as exc:
            fallback = self._fallback_act(state, knowledge_context)
            fallback["inference_source"] = "fallback_rules"
            fallback["checkpoint_error"] = str(exc)
            return fallback

    def _act_with_checkpoint(
        self,
        state: dict[str, Any],
        knowledge_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        table, threshold_source = self._threshold_table(knowledge_context)

        return {
            "model": "CMFBE-ST-GCN",
            "checkpoint_path": self.checkpoint_path,
            "inference_source": "checkpoint",
            "process_decomposition": processes,
            "net_change": physics_delta,
            "thresholds": {feature: entry["threshold"] for feature, entry in table.items()},
            "threshold_source": threshold_source,
            "threshold_breaches": self._threshold_breaches(state, table),
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

    def _fallback_act(
        self,
        state: dict[str, Any],
        knowledge_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Extract features for process decomposition
        rainfall_3d = state.get("rainfall_3d", 0.0)
        huangdu_flow = state.get("huangdu_flow_m3s", 0.0)
        turbidity_7d_mean = state.get("turbidity_7d_mean", 0.0)
        chlorophyll = state.get("chlorophyll_a", 0.0)

        # The thresholds are the graph's, not this file's. The rule-based
        # process decomposition below is still this file's own — the graph
        # carries critical levels, not the coefficients these formulas need —
        # and ``inference_source: fallback_rules`` is what says so.
        table, threshold_source = self._threshold_table(knowledge_context)

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
        threshold_breaches = self._threshold_breaches(state, table)

        return {
            "model": "CMFBE-ST-GCN",
            "checkpoint_path": self.checkpoint_path,
            "process_decomposition": processes,
            "net_change": float(net_turbidity_change),
            "thresholds": {feature: entry["threshold"] for feature, entry in table.items()},
            "threshold_source": threshold_source,
            "threshold_breaches": threshold_breaches,
            "predictions": {
                "next_day_turbidity_trend": "increasing" if net_turbidity_change > 0 else "decreasing",
                "confidence": 0.74,  # From README baseline
            },
        }

    def _threshold_table(
        self, knowledge_context: dict[str, Any] | None
    ) -> tuple[dict[str, dict[str, Any]], str]:
        """The critical levels to measure against, and where they came from.

        Two answers, and the caller is told which it got:

        1. **The threshold graph, sent by the platform.** Each node carries its
           unit and, with them, the fit that justifies the level — ``r2_gain``
           and ``response_jump`` — so a breach can say why 49.1 mm is critical
           and not merely that it is.
        2. **Nothing**, reported as ``unavailable`` with no breaches.

        There is deliberately no third answer. This file used to hold four of
        these numbers as literals, and ``agent/outputs/thresholds/`` ships a
        snapshot of the CSV they were taken from — a snapshot that has since
        gone stale, with 4 of its 10 levels disagreeing with the platform's,
        ``wind_speed`` among them by a factor of 2.7. Reading either would mean
        screening against levels the platform does not recognise, and doing it
        without saying so. A caller who wants threshold screening has to send
        the graph; the platform always does.
        """
        table = self._thresholds_from_context(knowledge_context)
        if table:
            return table, THRESHOLD_SOURCE_GRAPH
        return {}, THRESHOLD_SOURCE_NONE

    @staticmethod
    def _thresholds_from_context(
        knowledge_context: dict[str, Any] | None
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(knowledge_context, dict):
            return {}
        section = knowledge_context.get("thresholds")
        if not isinstance(section, dict) or not section.get("available"):
            return {}

        table: dict[str, dict[str, Any]] = {}
        for node in section.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            feature = str(node.get("feature") or "")
            threshold = _number(node.get("threshold"))
            # A node with no level is not a threshold. Defaulting it to 0.0
            # would report every measured value as a breach.
            if not feature or threshold is None:
                continue
            table[feature] = {
                "threshold": threshold,
                "unit": str(node.get("unit") or ""),
                "label": str(node.get("label") or ""),
                "graph_name": str(section.get("graph_name") or ""),
                "scope": str(section.get("scope") or ""),
                "r2_gain": _number(node.get("r2_gain")),
                "piecewise_r2": _number(node.get("piecewise_r2")),
                "response_jump": _number(node.get("response_jump")),
                "interpretation": str(node.get("interpretation") or ""),
            }
        return table

    def _threshold_breaches(
        self,
        state: dict[str, Any],
        table: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Every critical level the current state is above, with its evidence.

        Only features the state actually carries a value for are evaluated. The
        old version read four fixed names and defaulted each to ``0.0``, which
        is a silent claim that the rain gauge read zero — and against a negative
        or zero threshold that claim becomes a breach out of missing data.
        """
        breaches: list[dict[str, Any]] = []
        for feature, entry in table.items():
            value = _state_value(state, feature)
            if value is None:
                continue
            if value <= entry["threshold"]:
                continue
            breaches.append(
                {
                    # ``factor``/``value``/``threshold`` are the platform's
                    # documented shape. This used to emit
                    # ``{"threshold": <the feature's name>, "value": ...}``,
                    # which put a string under a numeric key and left the panel
                    # rendering ``rainfall_3d 41.00 / rainfall_3d``.
                    "factor": feature,
                    "value": value,
                    "threshold": entry["threshold"],
                    "unit": entry["unit"],
                    "label": entry["label"],
                    "r2_gain": entry["r2_gain"],
                    "response_jump": entry["response_jump"],
                    "interpretation": entry["interpretation"],
                }
            )
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
        # Loaded, not merely present — see ``MSCIMAgent.health``.
        loaded = self.runner.ready
        # Nothing about thresholds belongs here: whether this agent will screen
        # against them is decided per request by whether the platform sent the
        # graph, and a health check that read the stale local snapshot instead
        # would report a capability the agent does not have.
        return {
            "agent": self.name,
            "checkpoint": self.checkpoint_path,
            "status": "ready" if loaded else "degraded",
            "checkpoint_loaded": loaded,
            "checkpoint_error": self.runner.load_error,
        }
