from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.physics.cmfbe_surrogate import evaluate_cmfbe_surrogate


OUTPUT_DIR = PROJECT_ROOT / "outputs"
FEATURES_PATH = OUTPUT_DIR / "intermediate" / "multimodal_daily_dataset.csv"
PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
COEFFICIENTS_PATH = OUTPUT_DIR / "physics" / "physics_coefficients.json"
THRESHOLD_SUMMARY_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_threshold_summary.csv"
SENSITIVITY_DIR = OUTPUT_DIR / "sensitivity"
COUNTERFACTUAL_DIR = OUTPUT_DIR / "counterfactual"

SOBOL_CSV_PATH = SENSITIVITY_DIR / "cmfbe_sobol_indices.csv"
SOBOL_JSON_PATH = SENSITIVITY_DIR / "cmfbe_sobol_indices.json"
COUNTERFACTUAL_CSV_PATH = COUNTERFACTUAL_DIR / "cmfbe_counterfactual_summary.csv"
REPORT_MD_PATH = COUNTERFACTUAL_DIR / "cmfbe_sobol_counterfactual_report.md"

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


def build_sobol_problem(test_frame: pd.DataFrame) -> tuple[list[str], dict[str, tuple[float, float]]]:
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


def evaluate_response(frame: pd.DataFrame, coefficients: dict[str, object]) -> np.ndarray:
    evaluated = evaluate_cmfbe_surrogate(frame, coefficients)
    return evaluated["net_process_response"].to_numpy(dtype=float)


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
        rows.append(
            {
                "factor": factor,
                "lower_bound": bounds[factor][0],
                "upper_bound": bounds[factor][1],
                "first_order_index": first_order,
                "total_order_index": total_order,
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


def run_counterfactual_analysis(
    test_frame: pd.DataFrame,
    coefficients: dict[str, object],
    threshold_summary: pd.DataFrame,
    top_factors: list[str],
) -> pd.DataFrame:
    baseline = evaluate_cmfbe_surrogate(test_frame, coefficients)
    threshold_lookup = {
        str(row["feature"]): float(row["threshold"])
        for _, row in threshold_summary.iterrows()
        if row.get("status") == "ok" and pd.notna(row.get("threshold"))
    }

    rows: list[dict[str, object]] = []
    for factor in top_factors:
        if factor not in test_frame.columns:
            continue
        interventions: list[tuple[str, pd.Series]] = [
            ("minus_20pct", pd.to_numeric(test_frame[factor], errors="coerce") * 0.8),
            ("plus_20pct", pd.to_numeric(test_frame[factor], errors="coerce") * 1.2),
        ]
        if factor in threshold_lookup:
            interventions.append(
                (
                    "set_to_threshold",
                    pd.Series([threshold_lookup[factor]] * len(test_frame), index=test_frame.index),
                )
            )

        for intervention_name, intervention_values in interventions:
            cf_frame = test_frame.copy()
            cf_frame[factor] = intervention_values
            cf_eval = evaluate_cmfbe_surrogate(cf_frame, coefficients)
            rows.append(
                {
                    "factor": factor,
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
                }
            )

    return pd.DataFrame(rows).sort_values(
        ["mean_net_process_delta", "mean_turbidity_delta"], ascending=[False, False]
    )


def write_report(
    test_frame: pd.DataFrame,
    sobol_df: pd.DataFrame,
    counterfactual_df: pd.DataFrame,
) -> None:
    lines = [
        "# CMFBE Sobol And Counterfactual Prototype",
        "",
        "## 1. Scope",
        "",
        f"- Test window: `{test_frame['target_date'].min().date()}` to `{test_frame['target_date'].max().date()}`.",
        f"- Days analyzed: `{len(test_frame)}`.",
        "- Response analyzed: `net_process_response = source_total - sink_total` from the current learned CMFBE surrogate.",
        "- Status: prototype Sobol-style Monte Carlo sensitivity and one-factor counterfactual intervention analysis.",
        "",
        "## 2. Top Sobol Factors",
        "",
        "| Factor | First-order | Total-order |",
        "| --- | ---: | ---: |",
    ]
    for row in sobol_df.head(10).itertuples(index=False):
        lines.append(
            f"| {row.factor} | {row.first_order_index:.4f} | {row.total_order_index:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 3. Strongest Counterfactual Responses",
            "",
            "| Factor | Intervention | Mean net-process delta | Mean turbidity delta | Positive-day change |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    ranked_cf = counterfactual_df.reindex(
        counterfactual_df["mean_net_process_delta"].abs().sort_values(ascending=False).index
    )
    for row in ranked_cf.head(12).itertuples(index=False):
        lines.append(
            f"| {row.factor} | {row.intervention} | {row.mean_net_process_delta:.4f} | "
            f"{row.mean_turbidity_delta:.4f} | {row.positive_response_day_change:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 4. Guardrails",
            "",
            "- These Sobol indices are prototype Monte Carlo estimates over the current single-station CMFBE surrogate, not full calibrated hydrodynamic uncertainty indices.",
            "- These counterfactuals are one-factor interventions on the learned surrogate, not validated engineering treatment outcomes.",
            "- Use these outputs to prioritize mechanistic inspection and data collection, not to claim operational policy optimality.",
        ]
    )
    REPORT_MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    SENSITIVITY_DIR.mkdir(parents=True, exist_ok=True)
    COUNTERFACTUAL_DIR.mkdir(parents=True, exist_ok=True)

    test_frame = load_test_frame()
    coefficients = json.loads(COEFFICIENTS_PATH.read_text(encoding="utf-8"))
    threshold_summary = pd.read_csv(THRESHOLD_SUMMARY_PATH)

    sobol_df, sobol_summary = run_sobol_analysis(test_frame, coefficients)
    sobol_df.to_csv(SOBOL_CSV_PATH, index=False, encoding="utf-8-sig")
    SOBOL_JSON_PATH.write_text(
        json.dumps(sobol_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    top_factors = sobol_df.head(6)["factor"].tolist() if not sobol_df.empty else []
    counterfactual_df = run_counterfactual_analysis(
        test_frame=test_frame,
        coefficients=coefficients,
        threshold_summary=threshold_summary,
        top_factors=top_factors,
    )
    counterfactual_df.to_csv(COUNTERFACTUAL_CSV_PATH, index=False, encoding="utf-8-sig")
    write_report(test_frame, sobol_df, counterfactual_df)

    print(f"Saved Sobol indices: {SOBOL_CSV_PATH}")
    print(f"Saved Sobol summary: {SOBOL_JSON_PATH}")
    print(f"Saved counterfactual summary: {COUNTERFACTUAL_CSV_PATH}")
    print(f"Saved report: {REPORT_MD_PATH}")


if __name__ == "__main__":
    main()
