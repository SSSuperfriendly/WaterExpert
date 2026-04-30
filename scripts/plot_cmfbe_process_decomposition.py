from __future__ import annotations

import json
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
METRICS_PATH = OUTPUT_DIR / "metrics" / "metrics.json"
PLOT_PATH = OUTPUT_DIR / "plots" / "cmfbe_process_decomposition.png"
SUMMARY_PATH = OUTPUT_DIR / "diagnosis" / "cmfbe_process_decomposition_summary.csv"


SOURCE_COLUMNS = [
    "runoff_source",
    "erosion_source",
    "tidal_source",
    "phytoplankton_source",
]
SINK_COLUMNS = [
    "krone_deposition_sink",
    "flushing_sink",
    "purification_sink",
]
PROCESS_LABELS = {
    "runoff_source": "径流输入",
    "erosion_source": "再悬浮",
    "tidal_source": "潮汐滞留",
    "phytoplankton_source": "生态增殖",
    "krone_deposition_sink": "沉降絮凝",
    "flushing_sink": "冲刷外输",
    "purification_sink": "自净恢复",
}
PROCESS_COLORS = {
    "runoff_source": "#d1495b",
    "erosion_source": "#edae49",
    "tidal_source": "#f79256",
    "phytoplankton_source": "#b56576",
    "krone_deposition_sink": "#5b8e7d",
    "flushing_sink": "#2a9d8f",
    "purification_sink": "#4d908e",
}


def load_test_frame() -> pd.DataFrame:
    df = pd.read_csv(PREDICTIONS_PATH)
    frame = df[(df["model"] == "cmfbe_stgcn") & (df["split"] == "test")].copy()
    frame["target_date"] = pd.to_datetime(frame["target_date"])
    frame = frame.sort_values("target_date").reset_index(drop=True)
    return frame


def build_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in SOURCE_COLUMNS + SINK_COLUMNS:
        rows.append(
            {
                "process_key": column,
                "process_label": PROCESS_LABELS[column],
                "direction": "source" if column in SOURCE_COLUMNS else "sink",
                "mean_contribution": float(frame[column].mean()),
                "std_contribution": float(frame[column].std()),
                "max_contribution": float(frame[column].max()),
            }
        )
    summary = pd.DataFrame(rows)
    summary.to_csv(SUMMARY_PATH, index=False, encoding="utf-8-sig")
    return summary


def load_metrics() -> tuple[float, float]:
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    turbidity_r2 = float(metrics["cmfbe_stgcn"]["test"]["turbidity"]["r2"])
    clearness_r2 = float(metrics["cmfbe_stgcn"]["test"]["clearness"]["r2"])
    return turbidity_r2, clearness_r2


def configure_matplotlib() -> None:
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "#f8f6f1"
    plt.rcParams["axes.facecolor"] = "#fcfbf7"
    plt.rcParams["savefig.facecolor"] = "#f8f6f1"


def plot_process_decomposition(frame: pd.DataFrame, summary: pd.DataFrame) -> Path:
    configure_matplotlib()
    turbidity_r2, clearness_r2 = load_metrics()

    smooth = frame.copy()
    rolling_columns = SOURCE_COLUMNS + SINK_COLUMNS + [
        "physics_delta_log_turbidity",
        "actual_turbidity",
        "predicted_turbidity",
        "physics_turbidity",
    ]
    smooth[rolling_columns] = smooth[rolling_columns].rolling(5, min_periods=1).mean()

    dates = smooth["target_date"].to_numpy()

    fig = plt.figure(figsize=(15, 10), constrained_layout=True)
    gs = fig.add_gridspec(2, 1, height_ratios=[1.6, 1.0], hspace=0.36)

    ax_top = fig.add_subplot(gs[0, 0])
    source_stack = [smooth[column].to_numpy() for column in SOURCE_COLUMNS]
    sink_stack = [-smooth[column].to_numpy() for column in SINK_COLUMNS]
    source_colors = [PROCESS_COLORS[column] for column in SOURCE_COLUMNS]
    sink_colors = [PROCESS_COLORS[column] for column in SINK_COLUMNS]

    ax_top.stackplot(
        dates,
        source_stack,
        colors=source_colors,
        alpha=0.85,
        labels=[PROCESS_LABELS[column] for column in SOURCE_COLUMNS],
    )
    ax_top.stackplot(
        dates,
        sink_stack,
        colors=sink_colors,
        alpha=0.85,
        labels=[PROCESS_LABELS[column] for column in SINK_COLUMNS],
    )
    ax_top.plot(
        dates,
        smooth["physics_delta_log_turbidity"],
        color="#1f2937",
        linewidth=2.0,
        label="机理净变化",
        zorder=6,
    )
    ax_top.axhline(0.0, color="#495057", linewidth=1.0, alpha=0.8)
    ax_top.set_title("CMFBE 致浊-去浊过程分解图", fontsize=18, fontweight="bold", pad=14)
    ax_top.set_ylabel("过程贡献强度\n(log turbidity/day)", fontsize=11)
    ax_top.grid(axis="y", alpha=0.18)
    ax_top.text(
        0.01,
        0.98,
        (
            "上方为致浊源项，下方为去浊汇项；黑线表示机理分支对次日浊度变化的净判断。\n"
            f"CMFBE 测试集表现：浊度 R²={turbidity_r2:.4f}，清澈度 proxy R²={clearness_r2:.4f}"
        ),
        transform=ax_top.transAxes,
        va="top",
        ha="left",
        fontsize=10.5,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#fffaf0", "edgecolor": "#c8b68c", "alpha": 0.95},
    )
    locator = mdates.AutoDateLocator(minticks=5, maxticks=8)
    formatter = mdates.ConciseDateFormatter(locator)
    ax_top.xaxis.set_major_locator(locator)
    ax_top.xaxis.set_major_formatter(formatter)
    ax_top.legend(ncols=4, loc="upper center", bbox_to_anchor=(0.5, -0.08), frameon=False)

    ax_bottom = fig.add_subplot(gs[1, 0])
    source_summary = summary[summary["direction"] == "source"].copy()
    sink_summary = summary[summary["direction"] == "sink"].copy()
    source_summary = source_summary.sort_values("mean_contribution", ascending=True)
    sink_summary = sink_summary.sort_values("mean_contribution", ascending=False)

    bottom_labels = [
        *sink_summary["process_label"].tolist(),
        *source_summary["process_label"].tolist(),
    ]
    bottom_values = [
        *(-sink_summary["mean_contribution"]).tolist(),
        *(source_summary["mean_contribution"]).tolist(),
    ]
    bottom_colors = [
        *[PROCESS_COLORS[key] for key in sink_summary["process_key"]],
        *[PROCESS_COLORS[key] for key in source_summary["process_key"]],
    ]

    y_pos = np.arange(len(bottom_labels))
    ax_bottom.barh(y_pos, bottom_values, color=bottom_colors, alpha=0.92)
    ax_bottom.axvline(0.0, color="#495057", linewidth=1.0)
    ax_bottom.set_yticks(y_pos)
    ax_bottom.set_yticklabels(bottom_labels, fontsize=11)
    ax_bottom.set_xlabel("测试集平均贡献强度", fontsize=11)
    ax_bottom.grid(axis="x", alpha=0.18)
    ax_bottom.text(
        0.5,
        1.03,
        "测试集平均过程贡献\n左侧为去浊汇项，右侧为致浊源项；当前最强源项主要是径流输入与潮汐滞留，"
        "最强汇项主要是冲刷外输与沉降絮凝。",
        transform=ax_bottom.transAxes,
        va="bottom",
        ha="center",
        fontsize=9.6,
        linespacing=1.35,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#fffaf0", "edgecolor": "#c8b68c", "alpha": 0.92},
    )

    for idx, value in enumerate(bottom_values):
        offset = 0.01 if value >= 0 else -0.01
        ax_bottom.text(
            value + offset,
            idx,
            f"{abs(value):.3f}",
            va="center",
            ha="left" if value >= 0 else "right",
            fontsize=9.5,
            color="#2b2d42",
        )

    fig.text(
        0.985,
        0.012,
        "数据范围：CMFBE 测试集 92 天 | 平滑方式：5 日滚动均值 | 输出文件：predictions.csv",
        ha="right",
        va="bottom",
        fontsize=9,
        color="#5c6770",
    )
    PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOT_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return PLOT_PATH


def main() -> None:
    frame = load_test_frame()
    summary = build_summary(frame)
    output = plot_process_decomposition(frame, summary)
    print(f"Saved plot to: {output}")


if __name__ == "__main__":
    main()
