from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
FEATURES_PATH = OUTPUT_DIR / "intermediate" / "multimodal_daily_dataset.csv"
THRESHOLD_DIR = OUTPUT_DIR / "thresholds"
PLOT_DIR = OUTPUT_DIR / "plots"

SUMMARY_CSV = THRESHOLD_DIR / "cmfbe_threshold_summary.csv"
CONTEXT_CSV = THRESHOLD_DIR / "cmfbe_thresholds_by_context.csv"
REPORT_MD = THRESHOLD_DIR / "cmfbe_threshold_report.md"
PLOT_PATH = PLOT_DIR / "cmfbe_threshold_response_20260430.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export CMFBE threshold analysis artifacts."
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
    global PREDICTIONS_PATH
    global FEATURES_PATH
    global THRESHOLD_DIR
    global PLOT_DIR
    global SUMMARY_CSV
    global CONTEXT_CSV
    global REPORT_MD
    global PLOT_PATH

    OUTPUT_DIR = output_root.resolve()
    PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
    FEATURES_PATH = OUTPUT_DIR / "intermediate" / "multimodal_daily_dataset.csv"
    THRESHOLD_DIR = OUTPUT_DIR / "thresholds"
    PLOT_DIR = OUTPUT_DIR / "plots"
    SUMMARY_CSV = THRESHOLD_DIR / "cmfbe_threshold_summary.csv"
    CONTEXT_CSV = THRESHOLD_DIR / "cmfbe_thresholds_by_context.csv"
    REPORT_MD = THRESHOLD_DIR / "cmfbe_threshold_report.md"
    PLOT_PATH = PLOT_DIR / "cmfbe_threshold_response_20260430.png"


@dataclass(frozen=True)
class Candidate:
    feature: str
    label: str
    unit: str = ""


CANDIDATES = [
    Candidate("velocity_proxy", "Hydrodynamic velocity proxy", "dimensionless"),
    Candidate("bed_shear_proxy", "Bed shear proxy", "dimensionless"),
    Candidate("precipitation_3d", "3-day cumulative precipitation", "mm"),
    Candidate("precipitation_7d", "7-day cumulative precipitation", "mm"),
    Candidate("wind_speed", "Wind speed", "m/s"),
    Candidate("air_temp", "Air temperature", "degC"),
    Candidate("songpu_flow_m3s_abs", "Songpu absolute flow", "m3/s"),
    Candidate("huangdu_flow_m3s_abs", "Huangdu absolute flow", "m3/s"),
    Candidate("songpu_tidal_pumping_proxy", "Songpu tidal pumping proxy", "dimensionless"),
    Candidate("songpu_resuspension_potential", "Songpu resuspension potential", "proxy"),
    Candidate("songpu_flushing_potential", "Songpu flushing potential", "proxy"),
]

CONTEXT_LABELS = {
    "hydrodynamic_condition": "hydrodynamic condition",
    "rainfall_background": "rainfall background",
    "temperature_background": "temperature background",
}


def configure_matplotlib() -> None:
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "#f8f6f1"
    plt.rcParams["axes.facecolor"] = "#fcfbf7"
    plt.rcParams["savefig.facecolor"] = "#f8f6f1"


def load_analysis_frame() -> pd.DataFrame:
    predictions = pd.read_csv(PREDICTIONS_PATH)
    predictions = predictions[
        (predictions["model"] == "cmfbe_stgcn") & (predictions["split"] == "test")
    ].copy()
    predictions["target_date"] = pd.to_datetime(predictions["target_date"])

    features = pd.read_csv(FEATURES_PATH)
    features["date"] = pd.to_datetime(features["date"])

    keep_columns = [
        "date",
        "air_temp",
        "precipitation",
        "precipitation_3d",
        "precipitation_7d",
        "wind_speed",
        "songpu_flow_m3s_abs",
        "huangdu_flow_m3s_abs",
        "songpu_tidal_pumping_proxy",
        "songpu_resuspension_potential",
        "songpu_flushing_potential",
        "hydrodynamic_intensity",
    ]
    features = features[[column for column in keep_columns if column in features.columns]].copy()

    frame = predictions.merge(features, left_on="target_date", right_on="date", how="left")
    frame["net_process_response"] = frame["source_total"] - frame["sink_total"]
    frame["actual_minus_predicted_turbidity"] = (
        frame["actual_turbidity"] - frame["predicted_turbidity"]
    )
    frame["turbidity_response_label"] = np.where(
        frame["net_process_response"] >= 0.0, "net_turbidifying", "net_clearing"
    )
    frame["hydrodynamic_condition"] = tertile_label(
        frame["velocity_proxy"],
        low="low hydrodynamics",
        mid="moderate hydrodynamics",
        high="high hydrodynamics",
    )
    frame["rainfall_background"] = tertile_label(
        frame["precipitation_7d"],
        low="dry background",
        mid="normal rainfall background",
        high="heavy-rainfall background",
    )
    frame["temperature_background"] = tertile_label(
        frame["air_temp"],
        low="cool background",
        mid="mild background",
        high="warm background",
    )
    return frame


def tertile_label(
    values: pd.Series, low: str = "low", mid: str = "medium", high: str = "high"
) -> pd.Series:
    q1 = values.quantile(1 / 3)
    q2 = values.quantile(2 / 3)
    labels = np.where(values <= q1, low, np.where(values <= q2, mid, high))
    return pd.Series(labels, index=values.index)


def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) < 3:
        return np.nan
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if ss_tot <= 1e-12:
        return np.nan
    return 1.0 - ss_res / ss_tot


def linear_fit_predict(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    if len(np.unique(x)) < 2:
        return np.full_like(y, np.mean(y), dtype=float), np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        coef = np.polyfit(x, y, deg=1)
    pred = np.polyval(coef, x)
    return pred, float(coef[0])


def estimate_piecewise_threshold(
    data: pd.DataFrame, feature: str, response: str, min_side: int = 8
) -> dict[str, float | int | str]:
    subset = data[[feature, response]].replace([np.inf, -np.inf], np.nan).dropna()
    subset = subset.sort_values(feature)
    n = int(len(subset))
    if n < min_side * 2 or subset[feature].nunique() < 4:
        return {"n": n, "status": "insufficient"}

    x = subset[feature].to_numpy(dtype=float)
    y = subset[response].to_numpy(dtype=float)
    base_pred, base_slope = linear_fit_predict(x, y)
    base_r2 = r2_score(y, base_pred)

    candidates = np.unique(x[min_side : n - min_side])
    best: dict[str, float | int | str] | None = None
    for threshold in candidates:
        left = x <= threshold
        right = ~left
        if int(left.sum()) < min_side or int(right.sum()) < min_side:
            continue
        left_pred, left_slope = linear_fit_predict(x[left], y[left])
        right_pred, right_slope = linear_fit_predict(x[right], y[right])
        pred = np.empty_like(y, dtype=float)
        pred[left] = left_pred
        pred[right] = right_pred
        piecewise_r2 = r2_score(y, pred)
        gain = piecewise_r2 - base_r2 if np.isfinite(base_r2) else np.nan
        record = {
            "n": n,
            "status": "ok",
            "threshold": float(threshold),
            "linear_r2": float(base_r2),
            "piecewise_r2": float(piecewise_r2),
            "r2_gain": float(gain),
            "linear_slope": float(base_slope),
            "slope_below": float(left_slope),
            "slope_above": float(right_slope),
            "mean_response_below": float(np.mean(y[left])),
            "mean_response_above": float(np.mean(y[right])),
            "response_jump": float(np.mean(y[right]) - np.mean(y[left])),
            "below_count": int(left.sum()),
            "above_count": int(right.sum()),
        }
        if best is None or record["piecewise_r2"] > best["piecewise_r2"]:
            best = record

    return best if best is not None else {"n": n, "status": "insufficient"}


def build_threshold_tables(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    global_rows = []
    context_rows = []
    response = "net_process_response"
    candidate_lookup = {candidate.feature: candidate for candidate in CANDIDATES}

    for candidate in CANDIDATES:
        if candidate.feature not in frame.columns:
            continue
        result = estimate_piecewise_threshold(frame, candidate.feature, response)
        global_rows.append(
            {
                "scope": "global_test_set",
                "context": "all",
                "feature": candidate.feature,
                "feature_label": candidate.label,
                "unit": candidate.unit,
                "response": response,
                **result,
            }
        )

    for context_column, context_label in CONTEXT_LABELS.items():
        for context_value, group in frame.groupby(context_column):
            for feature in [
                "precipitation_7d",
                "bed_shear_proxy",
                "velocity_proxy",
                "wind_speed",
                "air_temp",
            ]:
                if feature not in frame.columns:
                    continue
                candidate = candidate_lookup[feature]
                result = estimate_piecewise_threshold(group, feature, response, min_side=5)
                context_rows.append(
                    {
                        "context_type": context_label,
                        "context": context_value,
                        "feature": candidate.feature,
                        "feature_label": candidate.label,
                        "unit": candidate.unit,
                        "response": response,
                        **result,
                    }
                )

    summary_df = pd.DataFrame(global_rows)
    context_df = pd.DataFrame(context_rows)
    THRESHOLD_DIR.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(SUMMARY_CSV, index=False, encoding="utf-8")
    context_df.to_csv(CONTEXT_CSV, index=False, encoding="utf-8")
    return summary_df, context_df


def confidence_label(row: pd.Series) -> str:
    if row.get("status") != "ok":
        return "insufficient"
    gain = float(row.get("r2_gain", 0.0))
    n = int(row.get("n", 0))
    if n >= 40 and gain >= 0.10:
        return "high"
    if n >= 25 and gain >= 0.05:
        return "medium"
    return "exploratory"


def write_report(frame: pd.DataFrame, summary_df: pd.DataFrame, context_df: pd.DataFrame) -> None:
    good = summary_df[summary_df["status"] == "ok"].copy()
    good["confidence"] = good.apply(confidence_label, axis=1)
    good = good.sort_values(["r2_gain", "piecewise_r2"], ascending=False)
    top = good.head(8)

    context_good = context_df[context_df["status"] == "ok"].copy()
    context_good["confidence"] = context_good.apply(confidence_label, axis=1)
    context_good = context_good.sort_values(["r2_gain", "piecewise_r2"], ascending=False)

    lines = [
        "# CMFBE-ST-GCN Threshold Response Analysis",
        "",
        "## 1. Analysis Scope",
        "",
        "- Source: `CMFBE-ST-GCN` test-window outputs from the current Wusongkou daily prototype.",
        f"- Window: `{frame['target_date'].min().date()}` to `{frame['target_date'].max().date()}`, `{len(frame)}` days.",
        "- Response variable: `net_process_response = source_total - sink_total`, representing net turbidity forcing after subtracting self-purification and export sinks.",
        "- Threshold meaning: an empirical critical level at which the prototype becomes more likely to shift toward self-purification failure or rapid turbidity increase.",
        "- Method: one-breakpoint piecewise linear fit, selected by maximum explanatory gain over a global linear fit.",
        "- Boundary: these are empirical thresholds from the current model-and-data configuration, not calibrated 2D hydrodynamic physical thresholds.",
        "",
        "## 2. Global Threshold Candidates",
        "",
        "| Factor | Threshold | Unit | Piecewise R2 | R2 Gain | Response Jump | Confidence |",
        "| --- | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for row in top.itertuples(index=False):
        lines.append(
            f"| {row.feature_label} | {row.threshold:.4f} | {row.unit} | "
            f"{row.piecewise_r2:.3f} | {row.r2_gain:.3f} | {row.response_jump:.3f} | "
            f"{row.confidence} |"
        )

    lines.extend(
        [
            "",
            "## 3. Contextual Threshold Candidates",
            "",
            "| Context Type | Context | Factor | Threshold | Unit | Piecewise R2 | R2 Gain | Response Jump | Confidence |",
            "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in context_good.head(18).itertuples(index=False):
        lines.append(
            f"| {row.context_type} | {row.context} | {row.feature_label} | "
            f"{row.threshold:.4f} | {row.unit} | {row.piecewise_r2:.3f} | "
            f"{row.r2_gain:.3f} | {row.response_jump:.3f} | {row.confidence} |"
        )

    lines.extend(
        [
            "",
            "## 4. Interpretable Takeaways",
            "",
            "The strongest empirical threshold signals remain concentrated in cumulative rainfall, hydrodynamic forcing, bed shear, and flushing-related transport indicators.",
            "",
            "In operational interpretation, exceedance of these thresholds should be read as a heightened likelihood that turbidity-driving processes will dominate over self-purification and export sinks in the current prototype.",
            "",
            "## 5. Next Data Requirements",
            "",
            "- Upgrade empirical thresholds to physically calibrated control thresholds by adding section velocity, depth, sediment grain size, critical shear stress, and observed suspended-sediment concentration.",
            "- Build spatial threshold maps by adding multi-station hydrodynamics or 2D hydrodynamic fields together with remote-sensing or UAV-derived clarity products.",
            "- Build counterfactual threshold analyses by adding engineering control, restoration intervention, and external loading event records.",
        ]
    )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def plot_threshold_response(frame: pd.DataFrame, summary_df: pd.DataFrame) -> None:
    configure_matplotlib()
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    good = summary_df[summary_df["status"] == "ok"].copy()
    good = good.sort_values(["r2_gain", "piecewise_r2"], ascending=False).head(4)
    if good.empty:
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    axes = axes.flatten()
    for ax, row in zip(axes, good.itertuples(index=False)):
        x = frame[row.feature]
        y = frame["net_process_response"]
        ax.scatter(x, y, s=32, alpha=0.72, color="#3b6f8f", edgecolor="white", linewidth=0.4)
        ax.axhline(0.0, color="#343a40", linewidth=1.0, alpha=0.7)
        ax.axvline(row.threshold, color="#c44536", linewidth=2.0, linestyle="--")
        ax.set_title(f"{row.feature_label} threshold {row.threshold:.3f}", fontsize=13, fontweight="bold")
        ax.set_xlabel(f"{row.feature_label} ({row.unit})")
        ax.set_ylabel("Net process response")
        ax.grid(alpha=0.18)

    fig.suptitle("CMFBE-ST-GCN empirical threshold responses", fontsize=18, fontweight="bold")
    fig.savefig(PLOT_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    configure_output_root(Path(args.output_root))
    frame = load_analysis_frame()
    summary_df, context_df = build_threshold_tables(frame)
    write_report(frame, summary_df, context_df)
    plot_threshold_response(frame, summary_df)
    print(f"Saved threshold summary: {SUMMARY_CSV}")
    print(f"Saved context thresholds: {CONTEXT_CSV}")
    print(f"Saved report: {REPORT_MD}")
    print(f"Saved plot: {PLOT_PATH}")


if __name__ == "__main__":
    main()
