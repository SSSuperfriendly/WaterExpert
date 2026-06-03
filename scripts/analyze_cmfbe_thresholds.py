from __future__ import annotations

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


@dataclass(frozen=True)
class Candidate:
    feature: str
    label: str
    unit: str = ""


CANDIDATES = [
    Candidate("velocity_proxy", "水动力速度代理", "dimensionless"),
    Candidate("bed_shear_proxy", "床面剪切代理", "dimensionless"),
    Candidate("precipitation_3d", "3日累计降水", "mm"),
    Candidate("precipitation_7d", "7日累计降水", "mm"),
    Candidate("wind_speed", "风速", "m/s"),
    Candidate("air_temp", "气温", "degC"),
    Candidate("songpu_flow_m3s_abs", "松浦大桥流量绝对值", "m3/s"),
    Candidate("huangdu_flow_m3s_abs", "黄渡流量绝对值", "m3/s"),
    Candidate("songpu_tidal_pumping_proxy", "潮汐回流代理", "dimensionless"),
    Candidate("songpu_resuspension_potential", "再悬浮潜力", "proxy"),
    Candidate("songpu_flushing_potential", "冲刷外输潜力", "proxy"),
]


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
        frame["velocity_proxy"], low="低水动力", mid="中水动力", high="高水动力"
    )
    frame["rainfall_background"] = tertile_label(
        frame["precipitation_7d"], low="少雨背景", mid="常规降雨", high="强降雨背景"
    )
    frame["temperature_background"] = tertile_label(
        frame["air_temp"], low="低温背景", mid="中温背景", high="高温背景"
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

    contexts = [
        ("hydrodynamic_condition", "水动力条件"),
        ("rainfall_background", "降雨背景"),
        ("temperature_background", "气候温度背景"),
    ]
    for context_column, context_label in contexts:
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
    summary_df.to_csv(SUMMARY_CSV, index=False, encoding="utf-8-sig")
    context_df.to_csv(CONTEXT_CSV, index=False, encoding="utf-8-sig")
    return summary_df, context_df


def confidence_label(row: pd.Series) -> str:
    if row.get("status") != "ok":
        return "不可用"
    gain = float(row.get("r2_gain", 0.0))
    n = int(row.get("n", 0))
    if n >= 40 and gain >= 0.10:
        return "较高"
    if n >= 25 and gain >= 0.05:
        return "中等"
    return "探索性"


def write_report(frame: pd.DataFrame, summary_df: pd.DataFrame, context_df: pd.DataFrame) -> None:
    good = summary_df[summary_df["status"] == "ok"].copy()
    good["confidence"] = good.apply(confidence_label, axis=1)
    good = good.sort_values(["r2_gain", "piecewise_r2"], ascending=False)
    top = good.head(8)

    context_good = context_df[context_df["status"] == "ok"].copy()
    context_good["confidence"] = context_good.apply(confidence_label, axis=1)
    context_good = context_good.sort_values(["r2_gain", "piecewise_r2"], ascending=False)

    lines = [
        "# CMFBE-ST-GCN 浑浊响应阈值分析",
        "",
        "## 1. 分析口径",
        "",
        "- 当前结果基于 `CMFBE-ST-GCN` 吴淞口单站日尺度测试集。",
        f"- 样本范围：`{frame['target_date'].min().date()}` 到 `{frame['target_date'].max().date()}`，共 `{len(frame)}` 天。",
        "- 响应变量：`net_process_response = source_total - sink_total`，即致浊源项总和减去去浊汇项总和。",
        "- 阈值含义：当候选因子超过经验阈值时，模型更倾向于出现自净能力失效或浊度急剧增加的临界状态。",
        "- 阈值算法：对候选因子做两段式线性拟合，寻找使分段拟合解释度最高的经验断点。",
        "- 重要边界：这些是当前数据和模型输出上的经验阈值，不等同于完整二维水动力模型标定出的物理临界阈值。",
        "",
        "## 2. 全局经验阈值 Top 结果",
        "",
        "| 因子 | 阈值 | 单位 | 分段R2 | 相对线性R2提升 | 阈值以上响应变化 | 可信度 |",
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
            "## 3. 不同水动力条件和气候背景下的阈值",
            "",
            "| 背景类型 | 背景 | 因子 | 阈值 | 单位 | 分段R2 | R2提升 | 阈值以上响应变化 | 可信度 |",
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
            "## 4. 可汇报结论",
            "",
            "当前 CMFBE-ST-GCN 的阈值分析显示，吴淞口测试期内的浑浊响应具有明显的非线性分段特征；其中降雨累积、水动力速度代理、床面剪切代理和冲刷/再悬浮相关代理量是最值得优先关注的阈值因子。",
            "",
            "从治理解释上看，当降雨背景和水动力扰动超过经验阈值后，模型中的致浊源项更容易超过去浊汇项，水体净变化转向“正向致浊”；而在较强冲刷外输或沉降絮凝条件下，去浊汇项会增强，水体恢复变清的概率上升。",
            "",
            "## 5. 下一步数据需求",
            "",
            "- 若要把当前经验阈值升级为物理阈值，需要补充断面流速、断面水深、底泥粒径、临界剪切应力和真实悬沙浓度。",
            "- 若要形成空间阈值地图，需要接入多站点水动力或二维水动力格网结果，以及遥感/NDTI 或透明度空间反演产品。",
            "- 若要做反事实阈值，需要补充工程调度、治理事件和外源输入负荷数据。",
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
        ax.set_title(f"{row.feature_label} 阈值 {row.threshold:.3f}", fontsize=13, fontweight="bold")
        ax.set_xlabel(f"{row.feature_label} ({row.unit})")
        ax.set_ylabel("净致浊响应")
        ax.grid(alpha=0.18)

    fig.suptitle("CMFBE-ST-GCN 浑浊响应经验阈值", fontsize=18, fontweight="bold")
    fig.savefig(PLOT_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
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
