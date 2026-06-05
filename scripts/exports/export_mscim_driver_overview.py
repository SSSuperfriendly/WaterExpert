from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
DIAGNOSIS_DIR = OUTPUT_DIR / "diagnosis"
PLOTS_DIR = OUTPUT_DIR / "plots"

DETAIL_PATH = DIAGNOSIS_DIR / "mscim_turbidity_factor_diagnosis_details.csv"
DOMAIN_PATH = DIAGNOSIS_DIR / "mscim_turbidity_domain_diagnosis.csv"
SUMMARY_PATH = DIAGNOSIS_DIR / "mscim_turbidity_factor_diagnosis_summary.csv"

TOP_FEATURES_PATH = DIAGNOSIS_DIR / "mscim_turbidity_top_driver_features.csv"
TOP_DOMAINS_PATH = DIAGNOSIS_DIR / "mscim_turbidity_top_driver_domains.csv"
PLOT_PATH = PLOTS_DIR / "mscim_turbidity_driver_overview_20260419.png"


def configure_matplotlib() -> None:
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "#f7f5ef"
    plt.rcParams["axes.facecolor"] = "#fcfbf8"
    plt.rcParams["savefig.facecolor"] = "#f7f5ef"


def load_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detail_df = pd.read_csv(DETAIL_PATH)
    domain_df = pd.read_csv(DOMAIN_PATH)
    summary_df = pd.read_csv(SUMMARY_PATH)
    return detail_df, domain_df, summary_df


def build_top_tables(
    detail_df: pd.DataFrame, domain_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    top_features = (
        detail_df[detail_df["feature"] != "turbidity"]
        .groupby(["feature", "feature_label"], as_index=False)["driver_score"]
        .mean()
        .sort_values("driver_score", ascending=False)
        .head(10)
    )
    top_domains = (
        domain_df[domain_df["direction"] == "driver"]
        .sort_values("score", ascending=False)
        .head(8)
        .reset_index(drop=True)
    )

    TOP_FEATURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    top_features.to_csv(TOP_FEATURES_PATH, index=False, encoding="utf-8-sig")
    top_domains.to_csv(TOP_DOMAINS_PATH, index=False, encoding="utf-8-sig")
    return top_features, top_domains


def add_bar_labels(ax: plt.Axes, values: np.ndarray, decimals: int = 3) -> None:
    max_value = max(values) if len(values) else 0.0
    offset = max_value * 0.015 if max_value > 0 else 0.01
    for idx, value in enumerate(values):
        ax.text(
            value + offset,
            idx,
            f"{value:.{decimals}f}",
            va="center",
            ha="left",
            fontsize=10,
            color="#22313f",
        )


def set_axis_right_padding(ax: plt.Axes, values: np.ndarray, pad_ratio: float = 0.20) -> None:
    max_value = max(values) if len(values) else 0.0
    upper = max_value * (1.0 + pad_ratio) if max_value > 0 else 1.0
    ax.set_xlim(0.0, upper)


def plot_overview(
    top_features: pd.DataFrame, top_domains: pd.DataFrame, sample_count: int
) -> Path:
    configure_matplotlib()
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    feature_labels = top_features["feature_label"].tolist()[::-1]
    feature_values = top_features["driver_score"].to_numpy()[::-1]
    domain_labels = top_domains["domain_label"].tolist()[::-1]
    domain_values = top_domains["score"].to_numpy()[::-1]

    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[0.85, 1.45],
        left=0.06,
        right=0.985,
        top=0.84,
        bottom=0.12,
        wspace=0.42,
    )

    ax_left = fig.add_subplot(gs[0, 0])
    left_colors = ["#1f6f8b", "#2f8f9d", "#3ba99c", "#6bbf59", "#92c5de", "#a1d99b", "#c7e9b4", "#d9f0a3"]
    ax_left.barh(domain_labels, domain_values, color=left_colors[: len(domain_labels)], alpha=0.95)
    ax_left.set_title("域级致浊因子", fontsize=18, fontweight="bold", pad=12)
    ax_left.set_xlabel("平均贡献分数", fontsize=12)
    set_axis_right_padding(ax_left, domain_values)
    ax_left.grid(axis="x", alpha=0.18)
    add_bar_labels(ax_left, domain_values)

    ax_right = fig.add_subplot(gs[0, 1])
    right_colors = [
        "#b34759",
        "#c85c5c",
        "#d97d54",
        "#e09f3e",
        "#e9c46a",
        "#7f5539",
        "#6a994e",
        "#4d908e",
        "#577590",
        "#8d99ae",
    ]
    ax_right.barh(feature_labels, feature_values, color=right_colors[: len(feature_labels)], alpha=0.95)
    ax_right.set_title("特征级致浊因子 Top10", fontsize=18, fontweight="bold", pad=12)
    ax_right.set_xlabel("平均贡献分数", fontsize=12)
    set_axis_right_padding(ax_right, feature_values)
    ax_right.grid(axis="x", alpha=0.18)
    add_bar_labels(ax_right, feature_values)

    fig.suptitle(
        "MSCIM 致浊因子诊断总览",
        fontsize=24,
        fontweight="bold",
        y=0.955,
    )
    fig.text(
        0.5,
        0.91,
        (
            "统计口径：MSCIM 测试集诊断结果"
            f"（n = {sample_count}，当前为吴淞口单站增强原型）"
        ),
        ha="center",
        va="center",
        fontsize=11.5,
        color="#495057",
    )
    fig.text(
        0.5,
        0.02,
        "说明：左图反映主导过程类别，右图反映可解释特征的平均致浊贡献；已排除目标变量“浊度”本身。",
        ha="center",
        va="center",
        fontsize=10.5,
        color="#5c6770",
    )

    fig.savefig(PLOT_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return PLOT_PATH


def main() -> None:
    detail_df, domain_df, summary_df = load_tables()
    top_features, top_domains = build_top_tables(detail_df, domain_df)
    plot_path = plot_overview(
        top_features=top_features,
        top_domains=top_domains,
        sample_count=len(summary_df),
    )

    print(f"Saved feature summary: {TOP_FEATURES_PATH}")
    print(f"Saved domain summary: {TOP_DOMAINS_PATH}")
    print(f"Saved plot: {plot_path}")


if __name__ == "__main__":
    main()
