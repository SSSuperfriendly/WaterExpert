from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.physics.cmfbe_surrogate import evaluate_cmfbe_surrogate
from water_ai.utils.io import ensure_dir, save_json


OUTPUT_DIR = PROJECT_ROOT / "outputs"
FEATURES_PATH = OUTPUT_DIR / "intermediate" / "multimodal_daily_dataset.csv"
PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
COEFFICIENTS_PATH = OUTPUT_DIR / "physics" / "physics_coefficients.json"
THRESHOLD_SUMMARY_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_threshold_summary.csv"
SENSITIVITY_DIR = OUTPUT_DIR / "sensitivity"
COUNTERFACTUAL_DIR = OUTPUT_DIR / "counterfactual"
AGENT_DIR = OUTPUT_DIR / "agent"

SOBOL_CSV_PATH = SENSITIVITY_DIR / "cmfbe_sobol_indices.csv"
SOBOL_JSON_PATH = SENSITIVITY_DIR / "cmfbe_sobol_indices.json"
COUNTERFACTUAL_CSV_PATH = COUNTERFACTUAL_DIR / "cmfbe_counterfactual_summary.csv"
JOINT_COUNTERFACTUAL_CSV_PATH = COUNTERFACTUAL_DIR / "cmfbe_joint_counterfactual_summary.csv"
REPORT_MD_PATH = COUNTERFACTUAL_DIR / "cmfbe_sobol_counterfactual_report.md"
AGENT_SUMMARY_PATH = AGENT_DIR / "cmfbe_mechanism_intervention_digest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Sobol and counterfactual analysis artifacts."
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default=str(OUTPUT_DIR),
        help="Artifact output root. Defaults to repository outputs/.",
    )
    return parser.parse_args()


def configure_output_root(output_root: Path) -> None:
    global OUTPUT_DIR
    global FEATURES_PATH
    global PREDICTIONS_PATH
    global COEFFICIENTS_PATH
    global THRESHOLD_SUMMARY_PATH
    global SENSITIVITY_DIR
    global COUNTERFACTUAL_DIR
    global AGENT_DIR
    global SOBOL_CSV_PATH
    global SOBOL_JSON_PATH
    global COUNTERFACTUAL_CSV_PATH
    global JOINT_COUNTERFACTUAL_CSV_PATH
    global REPORT_MD_PATH
    global AGENT_SUMMARY_PATH

    OUTPUT_DIR = output_root.resolve()
    FEATURES_PATH = OUTPUT_DIR / "intermediate" / "multimodal_daily_dataset.csv"
    PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
    COEFFICIENTS_PATH = OUTPUT_DIR / "physics" / "physics_coefficients.json"
    THRESHOLD_SUMMARY_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_threshold_summary.csv"
    SENSITIVITY_DIR = OUTPUT_DIR / "sensitivity"
    COUNTERFACTUAL_DIR = OUTPUT_DIR / "counterfactual"
    AGENT_DIR = OUTPUT_DIR / "agent"
    SOBOL_CSV_PATH = SENSITIVITY_DIR / "cmfbe_sobol_indices.csv"
    SOBOL_JSON_PATH = SENSITIVITY_DIR / "cmfbe_sobol_indices.json"
    COUNTERFACTUAL_CSV_PATH = COUNTERFACTUAL_DIR / "cmfbe_counterfactual_summary.csv"
    JOINT_COUNTERFACTUAL_CSV_PATH = (
        COUNTERFACTUAL_DIR / "cmfbe_joint_counterfactual_summary.csv"
    )
    REPORT_MD_PATH = COUNTERFACTUAL_DIR / "cmfbe_sobol_counterfactual_report.md"
    AGENT_SUMMARY_PATH = AGENT_DIR / "cmfbe_mechanism_intervention_digest.json"

SOBOL_FACTORS = [
    "precipitation_3d",
    "precipitation_7d",
    "songpu_flow_m3s_abs",
    "huangdu_flow_m3s_abs",
    "songpu_water_level_m_1d_diff",
    "runoff_sediment_pulse",
    "songpu_tidal_pumping_proxy",
    "water_temp",
    "tn",
    "tp",
    "conductivity",
    "songpu_flushing_potential",
    "dissolved_oxygen",
    "self_purification_index",
]

FACTOR_LABELS = {
    "precipitation_3d": "3-day cumulative precipitation",
    "precipitation_7d": "7-day cumulative precipitation",
    "songpu_flow_m3s_abs": "Songpu absolute flow",
    "huangdu_flow_m3s_abs": "Huangdu absolute flow",
    "songpu_water_level_m_1d_diff": "Songpu 1-day water-level jump",
    "runoff_sediment_pulse": "runoff sediment pulse",
    "songpu_tidal_pumping_proxy": "Songpu tidal pumping proxy",
    "water_temp": "water temperature",
    "tn": "total nitrogen",
    "tp": "total phosphorus",
    "conductivity": "conductivity",
    "songpu_flushing_potential": "Songpu flushing potential",
    "dissolved_oxygen": "dissolved oxygen",
    "self_purification_index": "self-purification index",
}


def load_test_frame() -> pd.DataFrame:
    predictions = pd.read_csv(PREDICTIONS_PATH)
    predictions = predictions[
        (predictions["model"] == "cmfbe_stgcn") & (predictions["split"] == "test")
    ].copy()
    predictions["target_date"] = pd.to_datetime(predictions["target_date"])

    features = pd.read_csv(FEATURES_PATH)
    features["date"] = pd.to_datetime(features["date"])
    merged = predictions.merge(features, left_on="target_date", right_on="date", how="left")
    return merged.sort_values("target_date").reset_index(drop=True)


def build_sobol_problem(
    test_frame: pd.DataFrame,
) -> tuple[list[str], dict[str, tuple[float, float]]]:
    bounds: dict[str, tuple[float, float]] = {}
    factors: list[str] = []
    for factor in SOBOL_FACTORS:
        if factor not in test_frame.columns:
            continue
        series = pd.to_numeric(test_frame[factor], errors="coerce").dropna()
        if series.nunique() < 4:
            continue
        lower = float(series.quantile(0.05))
        upper = float(series.quantile(0.95))
        if upper <= lower:
            continue
        bounds[factor] = (lower, upper)
        factors.append(factor)
    return factors, bounds


def evaluate_frame(frame: pd.DataFrame, coefficients: dict[str, object]) -> pd.DataFrame:
    return evaluate_cmfbe_surrogate(frame, coefficients)


def evaluate_response(frame: pd.DataFrame, coefficients: dict[str, object]) -> np.ndarray:
    return evaluate_frame(frame, coefficients)["net_process_response"].to_numpy(dtype=float)


def run_sobol_analysis(
    test_frame: pd.DataFrame,
    coefficients: dict[str, object],
    sample_count: int = 2048,
    seed: int = 42,
) -> tuple[pd.DataFrame, dict[str, object]]:
    factors, bounds = build_sobol_problem(test_frame)
    rng = np.random.default_rng(seed)

    numeric_columns = test_frame.select_dtypes(include=[np.number]).columns.tolist()
    base_state = test_frame[numeric_columns].median(numeric_only=True).to_dict()
    template = pd.DataFrame([base_state] * sample_count)

    dim = len(factors)
    if dim == 0:
        return pd.DataFrame(), {"status": "no_valid_factors"}

    A = rng.random((sample_count, dim))
    B = rng.random((sample_count, dim))
    for idx, factor in enumerate(factors):
        low, high = bounds[factor]
        A[:, idx] = low + (high - low) * A[:, idx]
        B[:, idx] = low + (high - low) * B[:, idx]

    frame_A = template.copy()
    frame_B = template.copy()
    for idx, factor in enumerate(factors):
        frame_A[factor] = A[:, idx]
        frame_B[factor] = B[:, idx]

    YA = evaluate_response(frame_A, coefficients)
    YB = evaluate_response(frame_B, coefficients)
    variance = float(np.var(np.concatenate([YA, YB]), ddof=1))
    rows = []
    if variance <= 1e-12:
        return pd.DataFrame(), {"status": "degenerate_variance"}

    for idx, factor in enumerate(factors):
        frame_ABi = frame_A.copy()
        frame_ABi[factor] = frame_B[factor]
        YABi = evaluate_response(frame_ABi, coefficients)
        first_order = float(np.mean(YB * (YABi - YA)) / variance)
        total_order = float(0.5 * np.mean(np.square(YA - YABi)) / variance)
        interaction_strength = float(max(total_order - first_order, 0.0))
        rows.append(
            {
                "factor": factor,
                "factor_label": FACTOR_LABELS.get(factor, factor),
                "lower_bound": bounds[factor][0],
                "upper_bound": bounds[factor][1],
                "first_order_index": first_order,
                "total_order_index": total_order,
                "interaction_strength": interaction_strength,
            }
        )

    sobol_df = pd.DataFrame(rows).sort_values(
        ["total_order_index", "first_order_index"], ascending=False
    )
    summary = {
        "status": "ok",
        "sample_count": sample_count,
        "response": "net_process_response",
        "top_factors": sobol_df.head(8).to_dict(orient="records"),
    }
    return sobol_df, summary


def _threshold_lookup(threshold_summary: pd.DataFrame) -> dict[str, float]:
    return {
        str(row["feature"]): float(row["threshold"])
        for _, row in threshold_summary.iterrows()
        if row.get("status") == "ok" and pd.notna(row.get("threshold"))
    }


def _intervention_candidates(
    series: pd.Series,
    factor: str,
    threshold_lookup: dict[str, float],
) -> list[tuple[str, pd.Series]]:
    numeric_series = pd.to_numeric(series, errors="coerce")
    candidates: list[tuple[str, pd.Series]] = [
        ("minus_20pct", numeric_series * 0.8),
        ("plus_20pct", numeric_series * 1.2),
    ]
    if factor in threshold_lookup:
        candidates.append(
            (
                "set_to_threshold",
                pd.Series(
                    [threshold_lookup[factor]] * len(numeric_series),
                    index=numeric_series.index,
                ),
            )
        )
    return candidates


def run_counterfactual_analysis(
    test_frame: pd.DataFrame,
    coefficients: dict[str, object],
    threshold_summary: pd.DataFrame,
    top_factors: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, Any]]]:
    baseline = evaluate_frame(test_frame, coefficients)
    threshold_lookup = _threshold_lookup(threshold_summary)

    rows: list[dict[str, Any]] = []
    best_actions: dict[str, dict[str, Any]] = {}
    for factor in top_factors:
        if factor not in test_frame.columns:
            continue
        for intervention_name, intervention_values in _intervention_candidates(
            test_frame[factor], factor, threshold_lookup
        ):
            cf_frame = test_frame.copy()
            cf_frame[factor] = intervention_values
            cf_eval = evaluate_frame(cf_frame, coefficients)
            row = {
                "factor": factor,
                "factor_label": FACTOR_LABELS.get(factor, factor),
                "intervention": intervention_name,
                "mean_net_process_delta": float(
                    (cf_eval["net_process_response"] - baseline["net_process_response"]).mean()
                ),
                "mean_turbidity_delta": float(
                    (cf_eval["physics_turbidity_next"] - baseline["physics_turbidity_next"]).mean()
                ),
                "positive_response_day_change": float(
                    (cf_eval["net_process_response"] >= 0.0).mean()
                    - (baseline["net_process_response"] >= 0.0).mean()
                ),
                "mean_source_total_delta": float(
                    (cf_eval["source_total"] - baseline["source_total"]).mean()
                ),
                "mean_sink_total_delta": float(
                    (cf_eval["sink_total"] - baseline["sink_total"]).mean()
                ),
                "improved_days_fraction": float(
                    (
                        cf_eval["physics_turbidity_next"]
                        < baseline["physics_turbidity_next"]
                    ).mean()
                ),
            }
            rows.append(row)

    counterfactual_df = pd.DataFrame(rows)
    if counterfactual_df.empty:
        return counterfactual_df, pd.DataFrame(), best_actions

    for factor, factor_df in counterfactual_df.groupby("factor", sort=False):
        best_row = factor_df.sort_values(
            ["mean_turbidity_delta", "mean_net_process_delta"]
        ).iloc[0]
        best_actions[factor] = best_row.to_dict()

    ranked_factors = (
        counterfactual_df.assign(abs_turbidity_delta=lambda df: df["mean_turbidity_delta"].abs())
        .sort_values(["abs_turbidity_delta", "improved_days_fraction"], ascending=[False, False])
        ["factor"]
        .drop_duplicates()
        .tolist()
    )

    joint_rows: list[dict[str, Any]] = []
    selected_factors = [factor for factor in ranked_factors if factor in best_actions][:3]
    for bundle_size in [2, 3]:
        bundle_factors = selected_factors[:bundle_size]
        if len(bundle_factors) < bundle_size:
            continue
        joint_frame = test_frame.copy()
        applied_actions = []
        additive_expectation = 0.0
        for factor in bundle_factors:
            action = best_actions[factor]
            additive_expectation += float(action["mean_turbidity_delta"])
            applied_actions.append(
                {
                    "factor": factor,
                    "factor_label": FACTOR_LABELS.get(factor, factor),
                    "intervention": action["intervention"],
                }
            )
            for candidate_name, intervention_values in _intervention_candidates(
                test_frame[factor], factor, threshold_lookup
            ):
                if candidate_name == action["intervention"]:
                    joint_frame[factor] = intervention_values
                    break
        joint_eval = evaluate_frame(joint_frame, coefficients)
        row = {
            "bundle_name": f"top_{bundle_size}_linked_intervention",
            "bundle_size": bundle_size,
            "factors": "|".join(bundle_factors),
            "factor_labels": "|".join(FACTOR_LABELS.get(factor, factor) for factor in bundle_factors),
            "interventions": "|".join(
                f"{item['factor']}::{item['intervention']}" for item in applied_actions
            ),
            "mean_net_process_delta": float(
                (joint_eval["net_process_response"] - baseline["net_process_response"]).mean()
            ),
            "mean_turbidity_delta": float(
                (joint_eval["physics_turbidity_next"] - baseline["physics_turbidity_next"]).mean()
            ),
            "positive_response_day_change": float(
                (joint_eval["net_process_response"] >= 0.0).mean()
                - (baseline["net_process_response"] >= 0.0).mean()
            ),
            "improved_days_fraction": float(
                (joint_eval["physics_turbidity_next"] < baseline["physics_turbidity_next"]).mean()
            ),
            "additive_single_factor_expectation": additive_expectation,
            "synergy_vs_additive": float(
                (
                    joint_eval["physics_turbidity_next"] - baseline["physics_turbidity_next"]
                ).mean()
                - additive_expectation
            ),
        }
        joint_rows.append(row)

    joint_counterfactual_df = pd.DataFrame(joint_rows).sort_values(
        ["mean_turbidity_delta", "mean_net_process_delta"],
        ascending=[True, True],
    )
    counterfactual_df = counterfactual_df.sort_values(
        ["mean_turbidity_delta", "mean_net_process_delta"],
        ascending=[True, True],
    )
    return counterfactual_df, joint_counterfactual_df, best_actions


def build_agent_summary(
    test_frame: pd.DataFrame,
    sobol_df: pd.DataFrame,
    counterfactual_df: pd.DataFrame,
    joint_counterfactual_df: pd.DataFrame,
) -> dict[str, Any]:
    strongest_single = (
        counterfactual_df.sort_values(["mean_turbidity_delta", "mean_net_process_delta"])
        .head(8)
        .to_dict(orient="records")
        if not counterfactual_df.empty
        else []
    )
    joint_records = (
        joint_counterfactual_df.sort_values(["mean_turbidity_delta", "mean_net_process_delta"])
        .to_dict(orient="records")
        if not joint_counterfactual_df.empty
        else []
    )
    return {
        "artifact_name": "cmfbe_mechanism_intervention_digest",
        "scope": "wusongkou_daily_prototype",
        "test_window_start": str(test_frame["target_date"].min().date()),
        "test_window_end": str(test_frame["target_date"].max().date()),
        "days_analyzed": int(len(test_frame)),
        "response_semantics": (
            "Negative deltas indicate lower surrogate turbidity pressure relative to the "
            "baseline test window."
        ),
        "top_sobol_factors": sobol_df.head(8).to_dict(orient="records"),
        "strongest_single_factor_counterfactuals": strongest_single,
        "joint_interventions": joint_records,
        "recommended_agent_queries": [
            "Which mechanism factors dominate the current CMFBE surrogate according to Sobol total-order indices?",
            "Which single-factor perturbations most reduce surrogate turbidity pressure?",
            "Do linked runoff-flushing-resuspension interventions outperform the sum of one-factor changes?",
        ],
        "guardrails": [
            "These results are surrogate-level mechanism probes, not validated engineering intervention outcomes.",
            "Joint interventions are linked factor perturbations on the learned surrogate, not operational control recommendations.",
            "Use this digest for retrieval, hypothesis ranking, and next-data planning only.",
        ],
    }


def write_report(
    test_frame: pd.DataFrame,
    sobol_df: pd.DataFrame,
    counterfactual_df: pd.DataFrame,
    joint_counterfactual_df: pd.DataFrame,
) -> None:
    lines = [
        "# CMFBE Sobol And Counterfactual Prototype",
        "",
        "## 1. Scope",
        "",
        f"- Test window: `{test_frame['target_date'].min().date()}` to `{test_frame['target_date'].max().date()}`.",
        f"- Days analyzed: `{len(test_frame)}`.",
        "- Response analyzed: `net_process_response = source_total - sink_total` from the current learned CMFBE surrogate.",
        "- Status: prototype Sobol-style Monte Carlo sensitivity, single-factor counterfactuals, and linked multi-factor interventions.",
        "",
        "## 2. Top Sobol Factors",
        "",
        "| Factor | First-order | Total-order | Interaction |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in sobol_df.head(10).itertuples(index=False):
        lines.append(
            f"| {row.factor} | {row.first_order_index:.4f} | {row.total_order_index:.4f} | {row.interaction_strength:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 3. Strongest Single-Factor Counterfactuals",
            "",
            "| Factor | Intervention | Mean net-process delta | Mean turbidity delta | Improved-day fraction |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    ranked_cf = counterfactual_df.reindex(
        counterfactual_df["mean_turbidity_delta"].sort_values().index
    )
    for row in ranked_cf.head(12).itertuples(index=False):
        lines.append(
            f"| {row.factor} | {row.intervention} | {row.mean_net_process_delta:.4f} | "
            f"{row.mean_turbidity_delta:.4f} | {row.improved_days_fraction:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 4. Linked Multi-Factor Interventions",
            "",
            "| Bundle | Factors | Mean turbidity delta | Improved-day fraction | Synergy vs additive |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in joint_counterfactual_df.itertuples(index=False):
        lines.append(
            f"| {row.bundle_name} | {row.factor_labels} | {row.mean_turbidity_delta:.4f} | "
            f"{row.improved_days_fraction:.4f} | {row.synergy_vs_additive:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 5. Guardrails",
            "",
            "- These Sobol indices are prototype Monte Carlo estimates over the current single-station CMFBE surrogate, not full calibrated hydrodynamic uncertainty indices.",
            "- These counterfactuals are surrogate interventions on learned mechanism factors, not validated engineering treatment outcomes.",
            "- Use these outputs to prioritize mechanistic inspection, linked-factor monitoring, and agent retrieval, not to claim operational policy optimality.",
        ]
    )
    REPORT_MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    configure_output_root(Path(args.output_root))
    ensure_dir(SENSITIVITY_DIR)
    ensure_dir(COUNTERFACTUAL_DIR)
    ensure_dir(AGENT_DIR)

    test_frame = load_test_frame()
    coefficients = json.loads(COEFFICIENTS_PATH.read_text(encoding="utf-8"))
    threshold_summary = pd.read_csv(THRESHOLD_SUMMARY_PATH)

    sobol_df, sobol_summary = run_sobol_analysis(test_frame, coefficients)
    sobol_df.to_csv(SOBOL_CSV_PATH, index=False, encoding="utf-8-sig")
    save_json(sobol_summary, SOBOL_JSON_PATH)

    top_factors = sobol_df.head(6)["factor"].tolist() if not sobol_df.empty else []
    counterfactual_df, joint_counterfactual_df, _ = run_counterfactual_analysis(
        test_frame=test_frame,
        coefficients=coefficients,
        threshold_summary=threshold_summary,
        top_factors=top_factors,
    )
    counterfactual_df.to_csv(COUNTERFACTUAL_CSV_PATH, index=False, encoding="utf-8-sig")
    joint_counterfactual_df.to_csv(
        JOINT_COUNTERFACTUAL_CSV_PATH, index=False, encoding="utf-8-sig"
    )
    write_report(test_frame, sobol_df, counterfactual_df, joint_counterfactual_df)

    agent_summary = build_agent_summary(
        test_frame=test_frame,
        sobol_df=sobol_df,
        counterfactual_df=counterfactual_df,
        joint_counterfactual_df=joint_counterfactual_df,
    )
    save_json(agent_summary, AGENT_SUMMARY_PATH)

    print(f"Saved Sobol indices: {SOBOL_CSV_PATH}")
    print(f"Saved Sobol summary: {SOBOL_JSON_PATH}")
    print(f"Saved counterfactual summary: {COUNTERFACTUAL_CSV_PATH}")
    print(f"Saved joint counterfactual summary: {JOINT_COUNTERFACTUAL_CSV_PATH}")
    print(f"Saved report: {REPORT_MD_PATH}")
    print(f"Saved agent summary: {AGENT_SUMMARY_PATH}")


if __name__ == "__main__":
    main()
