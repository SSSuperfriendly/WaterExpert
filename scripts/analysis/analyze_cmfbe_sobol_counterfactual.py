from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.physics.cmfbe_surrogate import evaluate_cmfbe_surrogate
from water_ai.utils.io import ensure_dir, save_json

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs"
SOBOL_SAMPLE_COUNT = 2048
SOBOL_SEED = 42
TOP_COUNTERFACTUAL_FACTOR_COUNT = 6
TOP_AGENT_FACTOR_COUNT = 8


@dataclass(frozen=True)
class SensitivityArtifacts:
    output_root: Path
    features_path: Path
    predictions_path: Path
    coefficients_path: Path
    threshold_summary_path: Path
    sensitivity_dir: Path
    counterfactual_dir: Path
    agent_dir: Path
    sobol_csv_path: Path
    sobol_json_path: Path
    counterfactual_csv_path: Path
    joint_counterfactual_csv_path: Path
    report_md_path: Path
    agent_summary_path: Path

    @classmethod
    def from_output_root(cls, output_root: Path) -> "SensitivityArtifacts":
        resolved_root = output_root.resolve()
        sensitivity_dir = resolved_root / "sensitivity"
        counterfactual_dir = resolved_root / "counterfactual"
        agent_dir = resolved_root / "agent"
        return cls(
            output_root=resolved_root,
            features_path=resolved_root / "intermediate" / "multimodal_daily_dataset.csv",
            predictions_path=resolved_root / "predictions" / "predictions.csv",
            coefficients_path=resolved_root / "physics" / "physics_coefficients.json",
            threshold_summary_path=resolved_root / "thresholds" / "cmfbe_threshold_summary.csv",
            sensitivity_dir=sensitivity_dir,
            counterfactual_dir=counterfactual_dir,
            agent_dir=agent_dir,
            sobol_csv_path=sensitivity_dir / "cmfbe_sobol_indices.csv",
            sobol_json_path=sensitivity_dir / "cmfbe_sobol_indices.json",
            counterfactual_csv_path=counterfactual_dir / "cmfbe_counterfactual_summary.csv",
            joint_counterfactual_csv_path=counterfactual_dir / "cmfbe_joint_counterfactual_summary.csv",
            report_md_path=counterfactual_dir / "cmfbe_sobol_counterfactual_report.md",
            agent_summary_path=agent_dir / "cmfbe_mechanism_intervention_digest.json",
        )


SOBOL_FACTORS: tuple[str, ...] = (
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
)

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Sobol and counterfactual analysis artifacts."
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Artifact output root. Defaults to repository outputs/.",
    )
    return parser.parse_args()


def ensure_output_dirs(artifacts: SensitivityArtifacts) -> None:
    ensure_dir(artifacts.sensitivity_dir)
    ensure_dir(artifacts.counterfactual_dir)
    ensure_dir(artifacts.agent_dir)


def load_test_frame(artifacts: SensitivityArtifacts) -> pd.DataFrame:
    predictions = pd.read_csv(artifacts.predictions_path)
    predictions = predictions[
        (predictions["model"] == "cmfbe_stgcn") & (predictions["split"] == "test")
    ].copy()
    predictions["target_date"] = pd.to_datetime(predictions["target_date"])

    features = pd.read_csv(artifacts.features_path)
    features["date"] = pd.to_datetime(features["date"])
    merged = predictions.merge(features, left_on="target_date", right_on="date", how="left")
    return merged.sort_values("target_date").reset_index(drop=True)


def load_coefficients(artifacts: SensitivityArtifacts) -> dict[str, object]:
    return json.loads(artifacts.coefficients_path.read_text(encoding="utf-8"))


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
        lower_bound = float(series.quantile(0.05))
        upper_bound = float(series.quantile(0.95))
        if upper_bound <= lower_bound:
            continue
        bounds[factor] = (lower_bound, upper_bound)
        factors.append(factor)
    return factors, bounds


def evaluate_frame(frame: pd.DataFrame, coefficients: dict[str, object]) -> pd.DataFrame:
    return evaluate_cmfbe_surrogate(frame, coefficients)


def evaluate_response(frame: pd.DataFrame, coefficients: dict[str, object]) -> np.ndarray:
    return evaluate_frame(frame, coefficients)["net_process_response"].to_numpy(dtype=float)


def run_sobol_analysis(
    test_frame: pd.DataFrame,
    coefficients: dict[str, object],
    sample_count: int = SOBOL_SAMPLE_COUNT,
    seed: int = SOBOL_SEED,
) -> tuple[pd.DataFrame, dict[str, object]]:
    factors, bounds = build_sobol_problem(test_frame)
    random_generator = np.random.default_rng(seed)

    numeric_columns = test_frame.select_dtypes(include=[np.number]).columns.tolist()
    base_state = test_frame[numeric_columns].median(numeric_only=True).to_dict()
    template = pd.DataFrame([base_state] * sample_count)

    dimension_count = len(factors)
    if dimension_count == 0:
        return pd.DataFrame(), {"status": "no_valid_factors"}

    sample_a = random_generator.random((sample_count, dimension_count))
    sample_b = random_generator.random((sample_count, dimension_count))
    for index, factor in enumerate(factors):
        lower_bound, upper_bound = bounds[factor]
        sample_a[:, index] = lower_bound + (upper_bound - lower_bound) * sample_a[:, index]
        sample_b[:, index] = lower_bound + (upper_bound - lower_bound) * sample_b[:, index]

    frame_a = template.copy()
    frame_b = template.copy()
    for index, factor in enumerate(factors):
        frame_a[factor] = sample_a[:, index]
        frame_b[factor] = sample_b[:, index]

    response_a = evaluate_response(frame_a, coefficients)
    response_b = evaluate_response(frame_b, coefficients)
    variance = float(np.var(np.concatenate([response_a, response_b]), ddof=1))
    if variance <= 1e-12:
        return pd.DataFrame(), {"status": "degenerate_variance"}

    rows: list[dict[str, Any]] = []
    for index, factor in enumerate(factors):
        frame_ab_i = frame_a.copy()
        frame_ab_i[factor] = frame_b[factor]
        response_ab_i = evaluate_response(frame_ab_i, coefficients)
        first_order = float(np.mean(response_b * (response_ab_i - response_a)) / variance)
        total_order = float(0.5 * np.mean(np.square(response_a - response_ab_i)) / variance)
        rows.append(
            {
                "factor": factor,
                "factor_label": FACTOR_LABELS.get(factor, factor),
                "lower_bound": bounds[factor][0],
                "upper_bound": bounds[factor][1],
                "first_order_index": first_order,
                "total_order_index": total_order,
                "interaction_strength": float(max(total_order - first_order, 0.0)),
            }
        )

    sobol_df = pd.DataFrame(rows).sort_values(
        ["total_order_index", "first_order_index"], ascending=False
    )
    return sobol_df, {
        "status": "ok",
        "sample_count": sample_count,
        "response": "net_process_response",
        "top_factors": sobol_df.head(TOP_AGENT_FACTOR_COUNT).to_dict(orient="records"),
    }


def threshold_lookup(threshold_summary: pd.DataFrame) -> dict[str, float]:
    return {
        str(row["feature"]): float(row["threshold"])
        for _, row in threshold_summary.iterrows()
        if row.get("status") == "ok" and pd.notna(row.get("threshold"))
    }


def intervention_candidates(
    series: pd.Series,
    factor: str,
    thresholds: dict[str, float],
) -> list[tuple[str, pd.Series]]:
    numeric_series = pd.to_numeric(series, errors="coerce")
    candidates: list[tuple[str, pd.Series]] = [
        ("minus_20pct", numeric_series * 0.8),
        ("plus_20pct", numeric_series * 1.2),
    ]
    if factor in thresholds:
        candidates.append(
            (
                "set_to_threshold",
                pd.Series([thresholds[factor]] * len(numeric_series), index=numeric_series.index),
            )
        )
    return candidates


def single_factor_counterfactual_row(
    *,
    factor: str,
    intervention_name: str,
    baseline: pd.DataFrame,
    counterfactual_eval: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "factor": factor,
        "factor_label": FACTOR_LABELS.get(factor, factor),
        "intervention": intervention_name,
        "mean_net_process_delta": float(
            (counterfactual_eval["net_process_response"] - baseline["net_process_response"]).mean()
        ),
        "mean_turbidity_delta": float(
            (counterfactual_eval["physics_turbidity_next"] - baseline["physics_turbidity_next"]).mean()
        ),
        "positive_response_day_change": float(
            (counterfactual_eval["net_process_response"] >= 0.0).mean()
            - (baseline["net_process_response"] >= 0.0).mean()
        ),
        "mean_source_total_delta": float(
            (counterfactual_eval["source_total"] - baseline["source_total"]).mean()
        ),
        "mean_sink_total_delta": float(
            (counterfactual_eval["sink_total"] - baseline["sink_total"]).mean()
        ),
        "improved_days_fraction": float(
            (counterfactual_eval["physics_turbidity_next"] < baseline["physics_turbidity_next"]).mean()
        ),
    }


def run_counterfactual_analysis(
    test_frame: pd.DataFrame,
    coefficients: dict[str, object],
    threshold_summary: pd.DataFrame,
    top_factors: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, Any]]]:
    baseline = evaluate_frame(test_frame, coefficients)
    thresholds = threshold_lookup(threshold_summary)

    rows: list[dict[str, Any]] = []
    best_actions: dict[str, dict[str, Any]] = {}
    for factor in top_factors:
        if factor not in test_frame.columns:
            continue
        for intervention_name, intervention_values in intervention_candidates(
            test_frame[factor], factor, thresholds
        ):
            counterfactual_frame = test_frame.copy()
            counterfactual_frame[factor] = intervention_values
            counterfactual_eval = evaluate_frame(counterfactual_frame, coefficients)
            rows.append(
                single_factor_counterfactual_row(
                    factor=factor,
                    intervention_name=intervention_name,
                    baseline=baseline,
                    counterfactual_eval=counterfactual_eval,
                )
            )

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
    for bundle_size in (2, 3):
        bundle_factors = selected_factors[:bundle_size]
        if len(bundle_factors) < bundle_size:
            continue
        joint_frame = test_frame.copy()
        additive_expectation = 0.0
        applied_actions: list[dict[str, str]] = []
        for factor in bundle_factors:
            action = best_actions[factor]
            additive_expectation += float(action["mean_turbidity_delta"])
            applied_actions.append(
                {
                    "factor": factor,
                    "factor_label": FACTOR_LABELS.get(factor, factor),
                    "intervention": str(action["intervention"]),
                }
            )
            for candidate_name, intervention_values in intervention_candidates(
                test_frame[factor], factor, thresholds
            ):
                if candidate_name == action["intervention"]:
                    joint_frame[factor] = intervention_values
                    break
        joint_eval = evaluate_frame(joint_frame, coefficients)
        joint_rows.append(
            {
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
                    (joint_eval["physics_turbidity_next"] - baseline["physics_turbidity_next"]).mean()
                    - additive_expectation
                ),
            }
        )

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
        .head(TOP_AGENT_FACTOR_COUNT)
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
        "top_sobol_factors": sobol_df.head(TOP_AGENT_FACTOR_COUNT).to_dict(orient="records"),
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
    artifacts: SensitivityArtifacts,
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
    ranked_counterfactual = counterfactual_df.reindex(
        counterfactual_df["mean_turbidity_delta"].sort_values().index
    )
    for row in ranked_counterfactual.head(12).itertuples(index=False):
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
    artifacts.report_md_path.write_text("\n".join(lines), encoding="utf-8")


def persist_outputs(
    *,
    artifacts: SensitivityArtifacts,
    sobol_df: pd.DataFrame,
    sobol_summary: dict[str, object],
    counterfactual_df: pd.DataFrame,
    joint_counterfactual_df: pd.DataFrame,
    agent_summary: dict[str, Any],
    test_frame: pd.DataFrame,
) -> None:
    sobol_df.to_csv(artifacts.sobol_csv_path, index=False, encoding="utf-8-sig")
    save_json(sobol_summary, artifacts.sobol_json_path)
    counterfactual_df.to_csv(artifacts.counterfactual_csv_path, index=False, encoding="utf-8-sig")
    joint_counterfactual_df.to_csv(
        artifacts.joint_counterfactual_csv_path,
        index=False,
        encoding="utf-8-sig",
    )
    write_report(test_frame, sobol_df, counterfactual_df, joint_counterfactual_df, artifacts)
    save_json(agent_summary, artifacts.agent_summary_path)


def run_analysis(artifacts: SensitivityArtifacts) -> dict[str, Path]:
    ensure_output_dirs(artifacts)
    test_frame = load_test_frame(artifacts)
    coefficients = load_coefficients(artifacts)
    threshold_summary = pd.read_csv(artifacts.threshold_summary_path)

    sobol_df, sobol_summary = run_sobol_analysis(test_frame, coefficients)
    top_factors = sobol_df.head(TOP_COUNTERFACTUAL_FACTOR_COUNT)["factor"].tolist() if not sobol_df.empty else []
    counterfactual_df, joint_counterfactual_df, _ = run_counterfactual_analysis(
        test_frame=test_frame,
        coefficients=coefficients,
        threshold_summary=threshold_summary,
        top_factors=top_factors,
    )
    agent_summary = build_agent_summary(
        test_frame=test_frame,
        sobol_df=sobol_df,
        counterfactual_df=counterfactual_df,
        joint_counterfactual_df=joint_counterfactual_df,
    )
    persist_outputs(
        artifacts=artifacts,
        sobol_df=sobol_df,
        sobol_summary=sobol_summary,
        counterfactual_df=counterfactual_df,
        joint_counterfactual_df=joint_counterfactual_df,
        agent_summary=agent_summary,
        test_frame=test_frame,
    )
    return {
        "sobol_csv": artifacts.sobol_csv_path,
        "sobol_json": artifacts.sobol_json_path,
        "counterfactual_csv": artifacts.counterfactual_csv_path,
        "joint_counterfactual_csv": artifacts.joint_counterfactual_csv_path,
        "report_md": artifacts.report_md_path,
        "agent_summary": artifacts.agent_summary_path,
    }


def main() -> None:
    args = parse_args()
    artifacts = SensitivityArtifacts.from_output_root(Path(args.output_root))
    outputs = run_analysis(artifacts)
    print(f"Saved Sobol indices: {outputs['sobol_csv']}")
    print(f"Saved Sobol summary: {outputs['sobol_json']}")
    print(f"Saved counterfactual summary: {outputs['counterfactual_csv']}")
    print(f"Saved joint counterfactual summary: {outputs['joint_counterfactual_csv']}")
    print(f"Saved report: {outputs['report_md']}")
    print(f"Saved agent summary: {outputs['agent_summary']}")


if __name__ == "__main__":
    main()
