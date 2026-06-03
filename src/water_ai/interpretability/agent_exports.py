from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


FEATURE_AGENT_LABELS = {
    "precipitation_3d": "3-day cumulative precipitation",
    "precipitation_7d": "7-day cumulative precipitation",
    "songpu_flushing_potential": "Songpu flushing potential",
    "huangdu_flow_m3s_abs": "Huangdu absolute flow",
    "songpu_flow_m3s_abs": "Songpu absolute flow",
    "songpu_resuspension_potential": "Songpu resuspension potential",
    "wind_speed": "wind speed",
    "velocity_proxy": "hydrodynamic velocity proxy",
    "bed_shear_proxy": "bed shear proxy",
    "air_temp": "air temperature",
}


def build_threshold_knowledge_graph(
    predictions: pd.DataFrame,
    threshold_summary: pd.DataFrame,
    threshold_context: pd.DataFrame,
) -> dict[str, Any]:
    latest_test = predictions[
        (predictions["model"] == "cmfbe_stgcn") & (predictions["split"] == "test")
    ].copy()
    latest_test["target_date"] = pd.to_datetime(latest_test["target_date"])

    top_thresholds = threshold_summary[threshold_summary["status"] == "ok"].copy()
    top_thresholds = top_thresholds.sort_values(
        ["r2_gain", "piecewise_r2"], ascending=False
    ).head(12)
    context_thresholds = threshold_context[threshold_context["status"] == "ok"].copy()
    context_thresholds = context_thresholds.sort_values(
        ["r2_gain", "piecewise_r2"], ascending=False
    ).head(24)

    knowledge_graph: dict[str, Any] = {
        "graph_name": "mechanism_parameter_threshold_knowledge_graph",
        "scope": "wusongkou_daily_prototype",
        "threshold_semantics": (
            "Thresholds denote empirical critical levels at which turbidity forcing tends to exceed "
            "self-purification capacity or turbidity tends to increase sharply in the current prototype."
        ),
        "risk_snapshot": {},
        "threshold_nodes": [],
        "contextual_threshold_nodes": [],
        "guardrails": [
            "Do not reinterpret these thresholds as calibrated 2D hydrodynamic physical thresholds.",
            "Use them for screening, triage, and agent reasoning within the Wusongkou daily prototype.",
            "Escalate to multi-station or physically calibrated workflows when spatial or control claims are requested.",
        ],
    }

    if not latest_test.empty:
        knowledge_graph["risk_snapshot"] = {
            "test_window_start": str(latest_test["target_date"].min().date()),
            "test_window_end": str(latest_test["target_date"].max().date()),
        }
        optional_risk_columns = [
            ("actual_critical_transition", "critical_transition_rate"),
            (
                "predicted_critical_transition_prob",
                "mean_predicted_critical_transition_probability",
            ),
            ("actual_self_purification_failure", "self_purification_failure_rate"),
            (
                "predicted_self_purification_failure_prob",
                "mean_predicted_self_purification_failure_probability",
            ),
            ("actual_turbidity_surge", "turbidity_surge_rate"),
            ("predicted_turbidity_surge_prob", "mean_predicted_turbidity_surge_probability"),
        ]
        for source_column, target_key in optional_risk_columns:
            if source_column in latest_test.columns:
                knowledge_graph["risk_snapshot"][target_key] = float(
                    latest_test[source_column].mean()
                )

    for row in top_thresholds.itertuples(index=False):
        knowledge_graph["threshold_nodes"].append(
            {
                "node_id": f"threshold::{row.feature}",
                "type": "threshold",
                "feature": row.feature,
                "agent_label": FEATURE_AGENT_LABELS.get(row.feature, row.feature),
                "threshold": float(row.threshold),
                "unit": row.unit,
                "response": row.response,
                "r2_gain": float(row.r2_gain),
                "piecewise_r2": float(row.piecewise_r2),
                "response_jump": float(row.response_jump),
                "interpretation": (
                    "Higher-than-threshold values are associated with stronger net turbidity forcing "
                    "or weaker self-purification in the current Wusongkou prototype."
                ),
            }
        )

    for row in context_thresholds.itertuples(index=False):
        knowledge_graph["contextual_threshold_nodes"].append(
            {
                "node_id": f"context_threshold::{row.context_type}::{row.context}::{row.feature}",
                "type": "contextual_threshold",
                "context_type": row.context_type,
                "context": row.context,
                "feature": row.feature,
                "agent_label": FEATURE_AGENT_LABELS.get(row.feature, row.feature),
                "threshold": float(row.threshold),
                "unit": row.unit,
                "r2_gain": float(row.r2_gain),
                "piecewise_r2": float(row.piecewise_r2),
                "response_jump": float(row.response_jump),
            }
        )
    return knowledge_graph


def build_agent_context(
    metrics: dict[str, Any],
    best_model_summary: dict[str, Any],
    threshold_kg: dict[str, Any],
) -> dict[str, Any]:
    test_models = {}
    for model_name, model_metrics in metrics.items():
        if model_name == "data" or "test" not in model_metrics:
            continue
        test_metrics = model_metrics["test"]
        record = {
            "turbidity_r2": float(test_metrics["turbidity"]["r2"]),
            "turbidity_rmse": float(test_metrics["turbidity"]["rmse"]),
            "clearness_r2": float(test_metrics["clearness"]["r2"]),
            "clearness_rmse": float(test_metrics["clearness"]["rmse"]),
        }
        for optional_key in [
            "self_purification_failure",
            "turbidity_surge",
            "critical_transition",
        ]:
            if optional_key in test_metrics:
                record[optional_key] = test_metrics[optional_key]
        test_models[model_name] = record

    return {
        "product_name": "WaterExpert",
        "scope": "wusongkou_daily_prototype",
        "purpose": (
            "Agent-facing context for turbidity evolution diagnosis, self-purification stress screening, "
            "and empirical threshold reasoning."
        ),
        "best_model_summary": best_model_summary,
        "test_models": test_models,
        "threshold_kg_path": "outputs/thresholds/mechanism_parameter_threshold_kg.json",
        "threshold_risk_snapshot": threshold_kg.get("risk_snapshot", {}),
        "guardrails": [
            "Current outputs support empirical diagnosis and screening, not calibrated operational control.",
            "Do not claim a full multi-station hydrodynamic model has been trained.",
            "Do not claim spatial boundary maps, Sobol sensitivity, or counterfactual control maps are available.",
        ],
        "recommended_agent_queries": [
            "Which factors are currently closest to empirical self-purification failure thresholds?",
            "What are the top turbidity drivers in the latest verified test window?",
            "Does the current scenario resemble a rainfall-driven, flow-driven, or mixed turbidity surge?",
            "What data or model gaps prevent stronger physical or spatial conclusions?",
        ],
    }


def save_agent_context(
    output_path: str | Path,
    metrics: dict[str, Any],
    best_model_summary: dict[str, Any],
    threshold_kg: dict[str, Any],
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    context = build_agent_context(
        metrics=metrics,
        best_model_summary=best_model_summary,
        threshold_kg=threshold_kg,
    )
    output_path.write_text(
        json.dumps(context, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
