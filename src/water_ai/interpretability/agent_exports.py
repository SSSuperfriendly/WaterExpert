from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
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

SCENARIO_DEFINITIONS = {
    "external_input": (
        "Rainfall-runoff dominated turbidity stress, usually expressed as elevated "
        "cumulative precipitation together with stronger runoff-driven source loading."
    ),
    "internal_release": (
        "Hydrodynamic resuspension dominated stress, usually expressed as stronger bed shear, "
        "resuspension potential, and erosion-related source terms."
    ),
    "algal_dominant": (
        "Warm, nutrient-sensitive biological turbidity stress, usually expressed as elevated "
        "temperature together with stronger phytoplankton-growth proxy contributions."
    ),
    "chronic_composite": (
        "Mixed or persistent compound stress, usually expressed as multiple moderate drivers, "
        "weaker self-purification support, and no single dominant forcing mode."
    ),
}

SCENARIO_AGENT_LABELS = {
    "external_input": "external input",
    "internal_release": "internal release",
    "algal_dominant": "algal dominant",
    "chronic_composite": "chronic composite",
}

SCENARIO_RESPONSE_PLAYBOOK = {
    "external_input": {
        "response_focus": "reduce external loading pressure and verify runoff pulse persistence",
        "recommended_actions": [
            "Prioritize storm-event sampling, upstream inflow checks, and external-loading verification.",
            "Track whether cumulative rainfall and runoff proxies remain above empirical stress levels over the next 1 to 3 days.",
            "Review drainage, interception, or source-control records before attributing changes to in-channel restoration effects.",
        ],
        "monitoring_targets": [
            "3-day cumulative precipitation",
            "7-day cumulative precipitation",
            "runoff_source",
            "predicted_turbidity_surge_prob",
        ],
        "required_follow_up_data": [
            "event-scale inflow and suspended-sediment observations",
            "upstream discharge or drainage-operation records",
            "storm-linked pollutant and sediment loading observations",
        ],
        "forbidden_claims": [
            "Do not claim rainfall alone determines the full turbidity response.",
            "Do not claim intervention effectiveness without event-scale before/after evidence.",
        ],
    },
    "internal_release": {
        "response_focus": "verify resuspension stress and channel-internal sediment mobilization",
        "recommended_actions": [
            "Prioritize bed-shear, resuspension, and hydraulic disturbance checks near the affected reach.",
            "Review whether strong flushing coincides with internal release, because export can mask short-term resuspension stress.",
            "Flag the case for sediment-state inspection before recommending engineering disturbance controls.",
        ],
        "monitoring_targets": [
            "bed_shear_proxy",
            "songpu_resuspension_potential",
            "erosion_source",
            "songpu_flushing_potential",
        ],
        "required_follow_up_data": [
            "near-bed suspended sediment and grain-size observations",
            "cross-section velocity and depth measurements",
            "ship traffic, dredging, or channel-disturbance records",
        ],
        "forbidden_claims": [
            "Do not claim critical shear-stress exceedance has been physically calibrated.",
            "Do not prescribe sediment engineering actions without direct sediment-state evidence.",
        ],
    },
    "algal_dominant": {
        "response_focus": "check ecological amplification and weakened self-purification support",
        "recommended_actions": [
            "Prioritize warm-period nutrient and chlorophyll-linked checks before interpreting the case as purely hydraulic.",
            "Review whether weak self-purification support coincides with elevated phytoplankton-related process contribution.",
            "Treat the case as a biological-turbidity hypothesis that needs ecological confirmation rather than a verified bloom diagnosis.",
        ],
        "monitoring_targets": [
            "air_temp",
            "phytoplankton_source",
            "nutrient_risk_index",
            "self_purification_index",
        ],
        "required_follow_up_data": [
            "chlorophyll-a or phytoplankton biomass observations",
            "nutrient speciation and dissolved oxygen observations",
            "ecological field notes for warm-period bloom or decay conditions",
        ],
        "forbidden_claims": [
            "Do not claim a bloom event has been directly observed from the current prototype outputs.",
            "Do not recommend ecological intervention without supporting biological measurements.",
        ],
    },
    "chronic_composite": {
        "response_focus": "treat the case as multi-driver chronic stress requiring broader review",
        "recommended_actions": [
            "Escalate the case for compound-driver review rather than attributing it to a single dominant cause.",
            "Check whether repeated threshold proximity, high auxiliary risk, and weak purification support persist across consecutive days.",
            "Use this class to trigger broader data collection and analyst review instead of narrow one-factor responses.",
        ],
        "monitoring_targets": [
            "predicted_critical_transition_prob",
            "predicted_self_purification_failure_prob",
            "self_purification_index",
            "songpu_flushing_potential",
        ],
        "required_follow_up_data": [
            "multi-day multi-factor field observations",
            "intervention and management log records",
            "broader multi-station or spatial observations for persistent stress tracing",
        ],
        "forbidden_claims": [
            "Do not collapse chronic composite cases into one-factor narratives without additional evidence.",
            "Do not claim an optimal governance policy exists from the current prototype outputs.",
        ],
    },
}

SCENARIO_FEATURE_COLUMNS = [
    "air_temp",
    "precipitation",
    "precipitation_3d",
    "precipitation_7d",
    "wind_speed",
    "songpu_flow_m3s_abs",
    "huangdu_flow_m3s_abs",
    "songpu_resuspension_potential",
    "songpu_flushing_potential",
    "runoff_proxy",
    "nutrient_risk_index",
    "self_purification_index",
    "hydrodynamic_intensity",
]


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


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _build_threshold_lookup(threshold_summary: pd.DataFrame) -> dict[str, float]:
    good = threshold_summary[threshold_summary["status"] == "ok"].copy()
    return {
        str(row["feature"]): float(row["threshold"])
        for _, row in good.iterrows()
        if pd.notna(row["threshold"])
    }


def _threshold_exceedance(
    row: pd.Series, threshold_lookup: dict[str, float], feature: str
) -> float:
    threshold = threshold_lookup.get(feature)
    value = _safe_float(row.get(feature))
    if threshold is None or value is None or threshold <= 0.0:
        return 0.0
    return max(value / threshold, 0.0)


def _quantile_score(frame: pd.DataFrame, column: str, value: Any) -> float:
    if column not in frame.columns:
        return 0.0
    series = pd.to_numeric(frame[column], errors="coerce").dropna()
    numeric_value = _safe_float(value)
    if series.empty or numeric_value is None:
        return 0.0
    q50 = float(series.quantile(0.50))
    q90 = float(series.quantile(0.90))
    if q90 <= q50 + 1e-12:
        return 0.0
    return float(np.clip((numeric_value - q50) / (q90 - q50), 0.0, 1.25))


def _inverse_quantile_score(frame: pd.DataFrame, column: str, value: Any) -> float:
    if column not in frame.columns:
        return 0.0
    series = pd.to_numeric(frame[column], errors="coerce").dropna()
    numeric_value = _safe_float(value)
    if series.empty or numeric_value is None:
        return 0.0
    q10 = float(series.quantile(0.10))
    q50 = float(series.quantile(0.50))
    if q50 <= q10 + 1e-12:
        return 0.0
    return float(np.clip((q50 - numeric_value) / (q50 - q10), 0.0, 1.25))


def _scenario_confidence_label(primary_score: float, secondary_score: float) -> str:
    margin = primary_score - secondary_score
    if primary_score >= 0.85 and margin >= 0.18:
        return "high"
    if primary_score >= 0.60 and margin >= 0.08:
        return "medium"
    return "exploratory"


def _scenario_risk_band(
    primary_score: float,
    critical_transition_prob: float | None,
    self_purification_failure_prob: float | None,
) -> str:
    if primary_score >= 0.95:
        return "high"
    if primary_score >= 0.72:
        return "heightened"
    if (
        critical_transition_prob is not None
        and critical_transition_prob >= 0.40
        or self_purification_failure_prob is not None
        and self_purification_failure_prob >= 0.40
    ):
        return "heightened"
    return "watch"


def _round_float(value: Any, digits: int = 4) -> float | None:
    numeric_value = _safe_float(value)
    if numeric_value is None:
        return None
    return round(numeric_value, digits)


def build_scenario_triage(
    predictions: pd.DataFrame,
    features: pd.DataFrame,
    threshold_summary: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    latest_test = predictions[
        (predictions["model"] == "cmfbe_stgcn") & (predictions["split"] == "test")
    ].copy()
    latest_test["target_date"] = pd.to_datetime(latest_test["target_date"])

    features = features.copy()
    features["date"] = pd.to_datetime(features["date"])
    keep_columns = [
        "date",
        *[column for column in SCENARIO_FEATURE_COLUMNS if column in features.columns],
    ]
    features = features[keep_columns].copy()
    frame = latest_test.merge(features, left_on="target_date", right_on="date", how="left")
    frame["net_process_response"] = frame["source_total"] - frame["sink_total"]

    threshold_lookup = _build_threshold_lookup(threshold_summary)
    records: list[dict[str, Any]] = []

    for _, row in frame.iterrows():
        rainfall_3d = _threshold_exceedance(row, threshold_lookup, "precipitation_3d")
        rainfall_7d = _threshold_exceedance(row, threshold_lookup, "precipitation_7d")
        bed_shear = _threshold_exceedance(row, threshold_lookup, "bed_shear_proxy")
        resuspension = _threshold_exceedance(
            row, threshold_lookup, "songpu_resuspension_potential"
        )
        flushing = _threshold_exceedance(row, threshold_lookup, "songpu_flushing_potential")
        air_temp = _threshold_exceedance(row, threshold_lookup, "air_temp")
        external_input_score = (
            0.32 * min(rainfall_3d, 1.5)
            + 0.20 * min(rainfall_7d, 1.5)
            + 0.22 * _quantile_score(frame, "runoff_source", row.get("runoff_source"))
            + 0.16 * _quantile_score(frame, "runoff_proxy", row.get("runoff_proxy"))
            + 0.10
            * _quantile_score(
                frame,
                "predicted_turbidity_surge_prob",
                row.get("predicted_turbidity_surge_prob"),
            )
        )
        internal_release_score = (
            0.28 * min(bed_shear, 1.5)
            + 0.24 * min(resuspension, 1.5)
            + 0.22 * _quantile_score(frame, "erosion_source", row.get("erosion_source"))
            + 0.14 * _quantile_score(frame, "velocity_proxy", row.get("velocity_proxy"))
            + 0.12 * (1.0 - min(flushing, 1.0))
        )
        algal_dominant_score = (
            0.28 * min(air_temp, 1.5)
            + 0.26
            * _quantile_score(frame, "phytoplankton_source", row.get("phytoplankton_source"))
            + 0.18
            * _quantile_score(frame, "nutrient_risk_index", row.get("nutrient_risk_index"))
            + 0.16
            * _inverse_quantile_score(
                frame, "self_purification_index", row.get("self_purification_index")
            )
            + 0.12
            * _inverse_quantile_score(
                frame, "hydrodynamic_intensity", row.get("hydrodynamic_intensity")
            )
        )
        exceedance_flags = [
            rainfall_3d >= 1.0,
            rainfall_7d >= 1.0,
            bed_shear >= 1.0,
            resuspension >= 1.0,
            air_temp >= 1.0,
            flushing < 1.0,
        ]
        multi_driver_fraction = float(sum(exceedance_flags)) / float(len(exceedance_flags))
        chronic_composite_score = (
            0.24 * multi_driver_fraction
            + 0.24
            * _quantile_score(
                frame,
                "predicted_critical_transition_prob",
                row.get("predicted_critical_transition_prob"),
            )
            + 0.18
            * _quantile_score(
                frame,
                "predicted_self_purification_failure_prob",
                row.get("predicted_self_purification_failure_prob"),
            )
            + 0.18
            * _inverse_quantile_score(
                frame, "self_purification_index", row.get("self_purification_index")
            )
            + 0.16 * (1.0 - min(flushing, 1.0))
        )

        scenario_scores = {
            "external_input": float(external_input_score),
            "internal_release": float(internal_release_score),
            "algal_dominant": float(algal_dominant_score),
            "chronic_composite": float(chronic_composite_score),
        }
        ordered_scores = sorted(
            scenario_scores.items(), key=lambda item: item[1], reverse=True
        )
        primary_scenario, primary_score = ordered_scores[0]
        secondary_scenario, secondary_score = ordered_scores[1]
        confidence = _scenario_confidence_label(primary_score, secondary_score)
        risk_band = _scenario_risk_band(
            primary_score=primary_score,
            critical_transition_prob=_safe_float(row.get("predicted_critical_transition_prob")),
            self_purification_failure_prob=_safe_float(
                row.get("predicted_self_purification_failure_prob")
            ),
        )

        evidence: list[str] = []
        if rainfall_3d >= 1.0:
            evidence.append(
                f"3-day precipitation exceeded threshold ({row.get('precipitation_3d'):.1f} mm)"
            )
        if rainfall_7d >= 1.0:
            evidence.append(
                f"7-day precipitation exceeded threshold ({row.get('precipitation_7d'):.1f} mm)"
            )
        if bed_shear >= 1.0:
            evidence.append(
                f"bed shear proxy exceeded threshold ({row.get('bed_shear_proxy'):.3f})"
            )
        if resuspension >= 1.0:
            evidence.append(
                "resuspension potential exceeded empirical threshold "
                f"({row.get('songpu_resuspension_potential'):.1f})"
            )
        if air_temp >= 1.0:
            evidence.append(f"air temperature exceeded warm threshold ({row.get('air_temp'):.1f} degC)")
        if flushing >= 1.0:
            evidence.append(
                f"flushing potential was strong ({row.get('songpu_flushing_potential'):.3f})"
            )
        elif row.get("songpu_flushing_potential") is not None:
            evidence.append(
                f"flushing potential remained below empirical threshold ({row.get('songpu_flushing_potential'):.3f})"
            )

        records.append(
            {
                "target_date": str(row["target_date"].date()),
                "primary_scenario": primary_scenario,
                "primary_scenario_label": SCENARIO_AGENT_LABELS[primary_scenario],
                "secondary_scenario": secondary_scenario,
                "secondary_scenario_label": SCENARIO_AGENT_LABELS[secondary_scenario],
                "primary_score": round(primary_score, 4),
                "secondary_score": round(secondary_score, 4),
                "scenario_confidence": confidence,
                "risk_band": risk_band,
                "predicted_critical_transition_prob": _round_float(
                    row.get("predicted_critical_transition_prob")
                ),
                "predicted_self_purification_failure_prob": _round_float(
                    row.get("predicted_self_purification_failure_prob")
                ),
                "predicted_turbidity_surge_prob": _round_float(
                    row.get("predicted_turbidity_surge_prob")
                ),
                "net_process_response": _round_float(row.get("net_process_response")),
                "runoff_source": _round_float(row.get("runoff_source")),
                "erosion_source": _round_float(row.get("erosion_source")),
                "phytoplankton_source": _round_float(row.get("phytoplankton_source")),
                "flushing_sink": _round_float(row.get("flushing_sink")),
                "purification_sink": _round_float(row.get("purification_sink")),
                "precipitation_3d": _round_float(row.get("precipitation_3d")),
                "precipitation_7d": _round_float(row.get("precipitation_7d")),
                "songpu_resuspension_potential": _round_float(
                    row.get("songpu_resuspension_potential")
                ),
                "songpu_flushing_potential": _round_float(
                    row.get("songpu_flushing_potential")
                ),
                "bed_shear_proxy": _round_float(row.get("bed_shear_proxy")),
                "velocity_proxy": _round_float(row.get("velocity_proxy")),
                "air_temp": _round_float(row.get("air_temp")),
                "evidence_summary": "; ".join(evidence[:4]),
            }
        )

    triage_df = pd.DataFrame(records)
    summary_counts = (
        triage_df["primary_scenario"].value_counts(dropna=False).sort_index().to_dict()
        if not triage_df.empty
        else {}
    )
    mean_scores = {
        scenario: round(float(triage_df.loc[triage_df["primary_scenario"] == scenario, "primary_score"].mean()), 4)
        for scenario in summary_counts
    }
    high_risk_days = []
    if not triage_df.empty:
        ranked = triage_df.sort_values(
            ["primary_score", "predicted_critical_transition_prob"],
            ascending=[False, False],
        ).head(12)
        high_risk_days = ranked[
            [
                "target_date",
                "primary_scenario",
                "primary_score",
                "risk_band",
                "predicted_critical_transition_prob",
                "evidence_summary",
            ]
        ].to_dict(orient="records")

    summary = {
        "artifact_name": "scenario_triage",
        "scope": "wusongkou_daily_prototype",
        "threshold_semantics": (
            "Scenario labels describe empirical forcing regimes under which turbidity transport "
            "and self-purification balance appear to shift in the current prototype."
        ),
        "classification_semantics": (
            "The current scenario layer is a deterministic empirical triage built from CMFBE "
            "process outputs, auxiliary risk scores, and exported threshold breakpoints."
        ),
        "scenario_definitions": SCENARIO_DEFINITIONS,
        "thresholds_used": {
            FEATURE_AGENT_LABELS.get(feature, feature): threshold
            for feature, threshold in threshold_lookup.items()
        },
        "test_window_start": (
            str(latest_test["target_date"].min().date()) if not latest_test.empty else None
        ),
        "test_window_end": (
            str(latest_test["target_date"].max().date()) if not latest_test.empty else None
        ),
        "scenario_counts": summary_counts,
        "mean_primary_scores_by_scenario": mean_scores,
        "high_priority_days": high_risk_days,
        "daily_records": triage_df.to_dict(orient="records"),
        "guardrails": [
            "Scenario labels are empirical prototype classifications, not validated operational incident labels.",
            "Do not claim these scenario tags imply optimal intervention policies or counterfactual treatment outcomes.",
            "Escalate to richer physical, ecological, or multi-station evidence before making governance or spatial-control claims.",
        ],
    }
    return triage_df, summary


def build_response_playbook(
    scenario_triage: dict[str, Any],
    threshold_kg: dict[str, Any],
) -> dict[str, Any]:
    scenario_counts = scenario_triage.get("scenario_counts", {})
    high_priority_days = scenario_triage.get("high_priority_days", [])
    threshold_nodes = threshold_kg.get("threshold_nodes", [])
    threshold_digest = []
    for node in threshold_nodes[:8]:
        threshold_digest.append(
            {
                "feature": node.get("feature"),
                "agent_label": node.get("agent_label"),
                "threshold": node.get("threshold"),
                "unit": node.get("unit"),
                "interpretation": node.get("interpretation"),
            }
        )

    scenario_responses = {}
    for scenario_name, playbook in SCENARIO_RESPONSE_PLAYBOOK.items():
        scenario_responses[scenario_name] = {
            "scenario_definition": SCENARIO_DEFINITIONS[scenario_name],
            "occurrence_count": int(scenario_counts.get(scenario_name, 0)),
            **playbook,
        }

    prioritized_cases = []
    for item in high_priority_days[:10]:
        scenario_name = item.get("primary_scenario")
        playbook = SCENARIO_RESPONSE_PLAYBOOK.get(scenario_name, {})
        prioritized_cases.append(
            {
                "target_date": item.get("target_date"),
                "scenario": scenario_name,
                "risk_band": item.get("risk_band"),
                "primary_score": item.get("primary_score"),
                "predicted_critical_transition_prob": item.get(
                    "predicted_critical_transition_prob"
                ),
                "evidence_summary": item.get("evidence_summary"),
                "response_focus": playbook.get("response_focus"),
                "monitoring_targets": playbook.get("monitoring_targets", []),
            }
        )

    return {
        "artifact_name": "agent_response_playbook",
        "scope": "wusongkou_daily_prototype",
        "purpose": (
            "Scenario-conditioned recommendation prototype for agent reasoning, follow-up monitoring, "
            "and guarded response drafting."
        ),
        "prototype_status": (
            "Deterministic playbook derived from empirical scenario triage and threshold artifacts. "
            "It is an agent-facing recommendation scaffold, not a trained RL-TGRR policy."
        ),
        "scenario_response_playbook": scenario_responses,
        "prioritized_cases": prioritized_cases,
        "threshold_digest": threshold_digest,
        "guardrails": [
            "Do not describe this artifact as a reinforcement-learning policy or optimal restoration controller.",
            "Do not treat the recommended actions as validated intervention prescriptions.",
            "Use this playbook for structured reasoning, triage, and follow-up planning only.",
        ],
        "future_extensions": [
            "Add counterfactual simulators only after intervention and response-outcome data are available.",
            "Add Sobol or Saltelli-based sensitivity artifacts only after parameterized uncertainty experiments are implemented.",
            "Upgrade to policy optimization only after action spaces, constraints, and reward definitions are explicitly validated.",
        ],
    }


def build_agent_context(
    metrics: dict[str, Any],
    best_model_summary: dict[str, Any],
    threshold_kg: dict[str, Any],
    scenario_triage: dict[str, Any] | None = None,
    response_playbook: dict[str, Any] | None = None,
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

    context = {
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
    if scenario_triage:
        context["scenario_triage_path"] = "outputs/agent/scenario_triage.json"
        context["scenario_counts"] = scenario_triage.get("scenario_counts", {})
        context["scenario_high_priority_days"] = scenario_triage.get(
            "high_priority_days", []
        )
    if response_playbook:
        context["response_playbook_path"] = "outputs/agent/response_playbook.json"
        context["recommended_agent_queries"].extend(
            [
                "What follow-up monitoring actions fit the current empirical scenario?",
                "Which guarded response template matches the latest high-priority case?",
            ]
        )
    return context


def save_agent_context(
    output_path: str | Path,
    metrics: dict[str, Any],
    best_model_summary: dict[str, Any],
    threshold_kg: dict[str, Any],
    scenario_triage: dict[str, Any] | None = None,
    response_playbook: dict[str, Any] | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    context = build_agent_context(
        metrics=metrics,
        best_model_summary=best_model_summary,
        threshold_kg=threshold_kg,
        scenario_triage=scenario_triage,
        response_playbook=response_playbook,
    )
    output_path.write_text(
        json.dumps(context, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def save_response_playbook(
    output_path: str | Path,
    scenario_triage: dict[str, Any],
    threshold_kg: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    playbook = build_response_playbook(
        scenario_triage=scenario_triage,
        threshold_kg=threshold_kg,
    )
    output_path.write_text(
        json.dumps(playbook, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path, playbook


def save_scenario_triage(
    output_json_path: str | Path,
    output_csv_path: str | Path,
    predictions: pd.DataFrame,
    features: pd.DataFrame,
    threshold_summary: pd.DataFrame,
) -> tuple[Path, Path, dict[str, Any]]:
    output_json_path = Path(output_json_path)
    output_csv_path = Path(output_csv_path)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    triage_df, summary = build_scenario_triage(
        predictions=predictions,
        features=features,
        threshold_summary=threshold_summary,
    )
    triage_df.to_csv(output_csv_path, index=False, encoding="utf-8")
    output_json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_json_path, output_csv_path, summary
