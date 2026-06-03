from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
SUMMARY_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_threshold_summary.csv"
CONTEXT_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_thresholds_by_context.csv"
OUTPUT_PATH = OUTPUT_DIR / "thresholds" / "mechanism_parameter_threshold_kg.json"


def build_knowledge_graph(
    predictions: pd.DataFrame,
    summary_df: pd.DataFrame,
    context_df: pd.DataFrame,
) -> dict:
    latest_test = predictions[
        (predictions["model"] == "cmfbe_stgcn") & (predictions["split"] == "test")
    ].copy()
    latest_test["target_date"] = pd.to_datetime(latest_test["target_date"])

    top_thresholds = summary_df[summary_df["status"] == "ok"].copy()
    top_thresholds = top_thresholds.sort_values(
        ["r2_gain", "piecewise_r2"], ascending=False
    ).head(12)
    context_thresholds = context_df[context_df["status"] == "ok"].copy()
    context_thresholds = context_thresholds.sort_values(
        ["r2_gain", "piecewise_r2"], ascending=False
    ).head(24)

    knowledge_graph = {
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
                "label": row.feature_label,
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
                "label": row.feature_label,
                "threshold": float(row.threshold),
                "unit": row.unit,
                "r2_gain": float(row.r2_gain),
                "piecewise_r2": float(row.piecewise_r2),
                "response_jump": float(row.response_jump),
            }
        )
    return knowledge_graph


def main() -> None:
    predictions = pd.read_csv(PREDICTIONS_PATH)
    summary_df = pd.read_csv(SUMMARY_PATH)
    context_df = pd.read_csv(CONTEXT_PATH)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            build_knowledge_graph(predictions, summary_df, context_df),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved threshold knowledge graph: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
