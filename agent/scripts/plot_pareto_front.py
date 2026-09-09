from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from water_ai.orchestrator.kpi import KPICalculator


OUTPUT_DIR = PROJECT_ROOT / "outputs"
SCENARIO_DIR = OUTPUT_DIR / "scenarios"
POLICY_DIR = OUTPUT_DIR / "policy"
PLOT_DIR = OUTPUT_DIR / "plots"

DEFAULT_CANDIDATES_PATH = POLICY_DIR / "pareto_candidates.csv"
DEFAULT_FRONT_PATH = POLICY_DIR / "pareto_front.csv"
DEFAULT_SUMMARY_PATH = POLICY_DIR / "pareto_summary.md"
DEFAULT_OUTPUT_PATH = PLOT_DIR / "pareto_front.png"

SCENARIO_LABELS = {
    "s1_external_input": "外源输入型",
    "s2_internal_release": "内源释放型",
    "s3_algae_bloom": "藻华主导型",
    "s4_chronic_combo": "慢性复合型",
}

ACTION_LABELS = {
    "release": "放水冲刷",
    "aeration": "曝气增氧",
    "combo": "组合调理",
    "selected": "当前多智能体策略",
    "policy_csv": "策略候选",
}

OBJECTIVE_COLUMNS = {
    "cost": ("energy_cost", "min"),
    "effect": ("turbidity_reduction_pct", "max"),
    "stability": ("stability", "max"),
}


@dataclass(frozen=True)
class SweepAction:
    policy: str
    release_rate: float = 0.0
    aeration_intensity: float = 0.0
    chemical_dosage: float = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot the WaterExpert Pareto frontier for cost-effect-stability trade-offs."
    )
    parser.add_argument(
        "--source",
        choices=["auto", "scenarios", "csv"],
        default="auto",
        help="Data source. 'auto' uses scenario outputs when available, otherwise a CSV.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Optional policy candidate CSV. Used when --source csv or when scenarios are unavailable.",
    )
    parser.add_argument(
        "--scenario-dir",
        type=Path,
        default=SCENARIO_DIR,
        help="Directory containing scenario */data.json files.",
    )
    parser.add_argument(
        "--optimize",
        nargs="+",
        default=["cost", "effect", "stability"],
        choices=sorted(OBJECTIVE_COLUMNS),
        help="Objectives used to compute non-dominated candidates.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Static PNG output path.",
    )
    parser.add_argument(
        "--html-output",
        type=Path,
        default=None,
        help="Optional interactive HTML output path. Defaults to the PNG path with .html suffix.",
    )
    parser.add_argument(
        "--candidates-output",
        type=Path,
        default=DEFAULT_CANDIDATES_PATH,
        help="CSV path for all candidate policies after metric normalization.",
    )
    parser.add_argument(
        "--front-output",
        type=Path,
        default=DEFAULT_FRONT_PATH,
        help="CSV path for the computed Pareto front.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=DEFAULT_SUMMARY_PATH,
        help="Markdown summary path.",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Skip the interactive Plotly HTML export.",
    )
    parser.add_argument(
        "--no-sweep",
        action="store_true",
        help="Use only the selected scenario policies; do not add scenario-informed sweep candidates.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    html_output = args.html_output or args.output.with_suffix(".html")

    frame, source_note = load_candidate_frame(args)
    if frame.empty:
        raise SystemExit("No Pareto candidates were found. Check --scenario-dir or --input.")

    frame = normalize_candidate_frame(frame)
    frame = compute_pareto_flags(frame, args.optimize)
    frame = score_candidates(frame)
    frame = frame.sort_values(
        ["is_pareto", "balanced_score", "turbidity_reduction_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    write_outputs(
        frame=frame,
        source_note=source_note,
        optimize=args.optimize,
        candidates_output=args.candidates_output,
        front_output=args.front_output,
        summary_output=args.summary_output,
    )
    render_static_png(frame, args.output, args.optimize, source_note)
    if not args.no_html:
        render_interactive_html(frame, html_output, args.optimize, source_note)

    print(f"Saved candidates: {args.candidates_output}")
    print(f"Saved Pareto front: {args.front_output}")
    print(f"Saved summary: {args.summary_output}")
    print(f"Saved static plot: {args.output}")
    if not args.no_html:
        print(f"Saved interactive plot: {html_output}")


def load_candidate_frame(args: argparse.Namespace) -> tuple[pd.DataFrame, str]:
    scenario_paths = sorted(args.scenario_dir.glob("s*/data.json"))
    if args.source in {"auto", "scenarios"} and scenario_paths:
        frame = build_frame_from_scenarios(scenario_paths, include_sweep=not args.no_sweep)
        return frame, f"scenario outputs: {args.scenario_dir}"

    input_path = args.input or DEFAULT_FRONT_PATH
    if args.source in {"auto", "csv"} and input_path.exists():
        frame = pd.read_csv(input_path)
        if "source" not in frame.columns:
            frame["source"] = "policy_csv"
        return frame, f"policy CSV: {input_path}"

    if args.source == "scenarios":
        raise SystemExit(f"No scenario data found under {args.scenario_dir}")
    raise SystemExit(f"No candidate CSV found at {input_path}")


def build_frame_from_scenarios(paths: list[Path], include_sweep: bool) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        scenario = path.parent.name
        episodes = data.get("episodes", [])
        if not episodes:
            continue

        selected_rows = selected_policy_rows(scenario, episodes)
        rows.extend(selected_rows)

        if include_sweep:
            base_turbidity = average_state_value(episodes, "turbidity", default=5.0)
            for idx, action in enumerate(scenario_sweep(scenario), start=1):
                rows.append(
                    candidate_row(
                        scenario=scenario,
                        candidate_id=f"{scenario}_sweep_{idx:03d}",
                        policy=action.policy,
                        action={
                            "release_rate": action.release_rate,
                            "aeration_intensity": action.aeration_intensity,
                            "chemical_dosage": action.chemical_dosage,
                        },
                        state={"turbidity": base_turbidity},
                        source="scenario_sweep",
                        is_selected=False,
                    )
                )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    group_cols = [
        "scenario",
        "scenario_label",
        "policy",
        "release_rate",
        "aeration_intensity",
        "chemical_dosage",
    ]
    metric_cols = [
        "turbidity_reduction",
        "turbidity_reduction_ratio",
        "energy_cost",
        "stability",
        "response_time_hours",
        "action_magnitude",
    ]
    grouped = (
        frame.groupby(group_cols, as_index=False)
        .agg(
            {
                **{col: "mean" for col in metric_cols},
                "source": lambda values: "+".join(sorted(set(map(str, values)))),
                "is_selected": "max",
                "candidate_id": "first",
            }
        )
        .sort_values(["scenario", "is_selected", "energy_cost"], ascending=[True, False, True])
        .reset_index(drop=True)
    )
    grouped["candidate_id"] = [
        f"{scenario}_{idx:03d}" for idx, scenario in enumerate(grouped["scenario"], start=1)
    ]
    return grouped


def selected_policy_rows(scenario: str, episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for idx, episode in enumerate(episodes, start=1):
        action = (
            episode.get("safety_check", {}).get("safe_action")
            or episode.get("execution", {}).get("action")
            or {}
        )
        state = episode.get("feedback", {}).get("state") or {}
        row = candidate_row(
            scenario=scenario,
            candidate_id=f"{scenario}_selected_{idx:03d}",
            policy="selected",
            action=action,
            state=state,
            source="multi_agent_episode",
            is_selected=True,
        )
        metrics = episode.get("metrics") or {}
        for key in [
            "turbidity_reduction",
            "turbidity_reduction_ratio",
            "energy_cost",
            "stability",
            "response_time_hours",
            "action_magnitude",
        ]:
            if key in metrics:
                row[key] = float(metrics[key])
        rows.append(row)
    return rows


def candidate_row(
    scenario: str,
    candidate_id: str,
    policy: str,
    action: dict[str, Any],
    state: dict[str, Any],
    source: str,
    is_selected: bool,
) -> dict[str, Any]:
    safe_action = {
        "release_rate": clamp_float(action.get("release_rate", 0.0), 0.0, 15.0),
        "aeration_intensity": clamp_float(action.get("aeration_intensity", 0.0), 0.0, 100.0),
        "chemical_dosage": clamp_float(action.get("chemical_dosage", 0.0), 0.0, 500.0),
    }
    metrics = KPICalculator().compute(safe_action, state)
    return {
        "candidate_id": candidate_id,
        "scenario": scenario,
        "scenario_label": SCENARIO_LABELS.get(scenario, scenario),
        "policy": policy,
        "policy_label": ACTION_LABELS.get(policy, policy),
        "source": source,
        "is_selected": bool(is_selected),
        **safe_action,
        **metrics,
    }


def scenario_sweep(scenario: str) -> list[SweepAction]:
    if scenario == "s1_external_input":
        return [
            SweepAction("release", release_rate=value)
            for value in np.linspace(1.5, 15.0, 10)
        ]
    if scenario == "s2_internal_release":
        return [
            SweepAction("release", release_rate=value)
            for value in np.linspace(0.8, 8.0, 10)
        ]
    if scenario == "s3_algae_bloom":
        return [
            SweepAction("aeration", aeration_intensity=value)
            for value in np.linspace(6.0, 72.0, 12)
        ]
    if scenario == "s4_chronic_combo":
        actions = [
            SweepAction("release", release_rate=value)
            for value in np.linspace(0.8, 6.4, 8)
        ]
        actions.extend(
            SweepAction("combo", release_rate=release, aeration_intensity=aeration)
            for release in np.linspace(0.8, 4.0, 5)
            for aeration in np.linspace(8.0, 40.0, 5)
        )
        return actions
    return [
        SweepAction("release", release_rate=release)
        for release in np.linspace(1.0, 10.0, 10)
    ]


def average_state_value(
    episodes: list[dict[str, Any]], key: str, default: float
) -> float:
    values = []
    for episode in episodes:
        value = episode.get("feedback", {}).get("state", {}).get(key)
        if is_finite_number(value):
            values.append(float(value))
    return float(np.mean(values)) if values else default


def normalize_candidate_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(column).strip() for column in frame.columns]

    rename_map = {
        "cost": "energy_cost",
        "cost_per_day": "energy_cost",
        "daily_cost": "energy_cost",
        "effect": "turbidity_reduction_pct",
        "effect_pct": "turbidity_reduction_pct",
        "reduction_pct": "turbidity_reduction_pct",
        "reduction_ratio": "turbidity_reduction_ratio",
    }
    for old, new in rename_map.items():
        if old in frame.columns and new not in frame.columns:
            frame[new] = frame[old]

    for column in ["release_rate", "aeration_intensity", "chemical_dosage"]:
        if column not in frame.columns:
            frame[column] = 0.0

    if "turbidity_reduction_pct" not in frame.columns:
        if "turbidity_reduction_ratio" in frame.columns:
            frame["turbidity_reduction_pct"] = frame["turbidity_reduction_ratio"].astype(float) * 100.0
        elif "turbidity_reduction" in frame.columns:
            values = frame["turbidity_reduction"].astype(float)
            frame["turbidity_reduction_pct"] = np.where(values <= 1.5, values * 100.0, values)
        else:
            frame["turbidity_reduction_pct"] = 0.0

    if "turbidity_reduction_ratio" not in frame.columns:
        frame["turbidity_reduction_ratio"] = frame["turbidity_reduction_pct"].astype(float) / 100.0
    if "turbidity_reduction" not in frame.columns:
        frame["turbidity_reduction"] = np.nan
    if "energy_cost" not in frame.columns:
        raise ValueError("Candidate frame must include energy_cost/cost/cost_per_day.")
    if "stability" not in frame.columns:
        frame["stability"] = np.nan
    if "response_time_hours" not in frame.columns:
        frame["response_time_hours"] = np.nan
    if "action_magnitude" not in frame.columns:
        frame["action_magnitude"] = (
            frame["release_rate"].astype(float).abs()
            + frame["aeration_intensity"].astype(float).abs() * 0.1
            + frame["chemical_dosage"].astype(float).abs() * 0.01
        )
    if "scenario" not in frame.columns:
        frame["scenario"] = "policy"
    if "scenario_label" not in frame.columns:
        frame["scenario_label"] = frame["scenario"].map(SCENARIO_LABELS).fillna(frame["scenario"])
    if "policy" not in frame.columns:
        frame["policy"] = "policy_csv"
    if "policy_label" not in frame.columns:
        frame["policy_label"] = frame["policy"].map(ACTION_LABELS).fillna(frame["policy"])
    if "source" not in frame.columns:
        frame["source"] = "policy_csv"
    if "is_selected" not in frame.columns:
        frame["is_selected"] = False
    if "candidate_id" not in frame.columns:
        frame["candidate_id"] = [f"candidate_{idx:03d}" for idx in range(1, len(frame) + 1)]

    numeric_columns = [
        "release_rate",
        "aeration_intensity",
        "chemical_dosage",
        "turbidity_reduction",
        "turbidity_reduction_ratio",
        "turbidity_reduction_pct",
        "energy_cost",
        "stability",
        "response_time_hours",
        "action_magnitude",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["is_selected"] = frame["is_selected"].astype(bool)
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame = frame.dropna(subset=["energy_cost", "turbidity_reduction_pct"]).reset_index(drop=True)
    frame["stability"] = frame["stability"].fillna(0.0).clip(0.0, 1.0)
    frame["energy_cost"] = frame["energy_cost"].clip(lower=0.0)
    frame["turbidity_reduction_pct"] = frame["turbidity_reduction_pct"].clip(lower=0.0)
    return frame


def compute_pareto_flags(frame: pd.DataFrame, objectives: list[str]) -> pd.DataFrame:
    frame = frame.copy()
    objective_specs = [OBJECTIVE_COLUMNS[name] for name in objectives]
    values = frame[[column for column, _ in objective_specs]].to_numpy(dtype=float)
    directions = [direction for _, direction in objective_specs]
    is_pareto = np.ones(len(frame), dtype=bool)

    for i in range(len(frame)):
        for j in range(len(frame)):
            if i == j:
                continue
            if dominates(values[j], values[i], directions):
                is_pareto[i] = False
                break

    frame["is_pareto"] = is_pareto
    return frame


def dominates(candidate: np.ndarray, other: np.ndarray, directions: list[str]) -> bool:
    better_or_equal = True
    strictly_better = False
    for idx, direction in enumerate(directions):
        left = candidate[idx]
        right = other[idx]
        if direction == "min":
            if left > right + 1e-9:
                better_or_equal = False
                break
            strictly_better = strictly_better or left < right - 1e-9
        else:
            if left < right - 1e-9:
                better_or_equal = False
                break
            strictly_better = strictly_better or left > right + 1e-9
    return better_or_equal and strictly_better


def score_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    cost_score = normalize_series(frame["energy_cost"], higher_is_better=False)
    effect_score = normalize_series(frame["turbidity_reduction_pct"], higher_is_better=True)
    stability_score = normalize_series(frame["stability"], higher_is_better=True)
    frame["balanced_score"] = (
        0.45 * effect_score + 0.35 * cost_score + 0.20 * stability_score
    )
    return frame


def normalize_series(values: pd.Series, higher_is_better: bool) -> pd.Series:
    values = values.astype(float)
    min_value = float(values.min())
    max_value = float(values.max())
    if math.isclose(max_value, min_value):
        return pd.Series(np.ones(len(values)), index=values.index)
    scaled = (values - min_value) / (max_value - min_value)
    return scaled if higher_is_better else 1.0 - scaled


def write_outputs(
    frame: pd.DataFrame,
    source_note: str,
    optimize: list[str],
    candidates_output: Path,
    front_output: Path,
    summary_output: Path,
) -> None:
    candidates_output.parent.mkdir(parents=True, exist_ok=True)
    front_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)

    output_columns = [
        "candidate_id",
        "scenario",
        "scenario_label",
        "policy",
        "policy_label",
        "source",
        "is_selected",
        "is_pareto",
        "balanced_score",
        "release_rate",
        "aeration_intensity",
        "chemical_dosage",
        "turbidity_reduction",
        "turbidity_reduction_ratio",
        "turbidity_reduction_pct",
        "energy_cost",
        "stability",
        "response_time_hours",
        "action_magnitude",
    ]
    available_columns = [column for column in output_columns if column in frame.columns]
    frame[available_columns].to_csv(candidates_output, index=False, encoding="utf-8-sig")
    frame.loc[frame["is_pareto"], available_columns].to_csv(
        front_output, index=False, encoding="utf-8-sig"
    )
    summary_output.write_text(
        build_summary_markdown(frame, source_note, optimize),
        encoding="utf-8",
    )


def build_summary_markdown(frame: pd.DataFrame, source_note: str, optimize: list[str]) -> str:
    front = frame[frame["is_pareto"]].copy()
    selected = frame[frame["is_selected"]].copy()
    knee = front.sort_values("balanced_score", ascending=False).head(1)

    lines = [
        "# WaterExpert 帕累托前沿摘要",
        "",
        f"- 数据来源：{source_note}",
        f"- 优化目标：{', '.join(optimize)}",
        f"- 候选策略数：{len(frame)}",
        f"- 非劣解数：{len(front)}",
    ]
    if not knee.empty:
        row = knee.iloc[0]
        lines.append(
            "- 推荐折中点："
            f"{row['scenario_label']} / {row['policy_label']}，"
            f"成本 ¥{row['energy_cost']:.0f}/day，"
            f"浊度削减 {row['turbidity_reduction_pct']:.1f}%，"
            f"稳定度 {row['stability']:.1%}"
        )
    if not selected.empty:
        selected_front = int(selected["is_pareto"].sum())
        lines.append(f"- 当前多智能体策略中位于前沿的数量：{selected_front}/{len(selected)}")

    lines.extend(["", "## Top Pareto Candidates", ""])
    lines.append("| 场景 | 策略 | 成本(¥/day) | 浊度削减率 | 稳定度 | 综合分 |")
    lines.append("|------|------|-------------|-----------|--------|--------|")
    top_rows = front.sort_values("balanced_score", ascending=False).head(8)
    for _, row in top_rows.iterrows():
        lines.append(
            f"| {row['scenario_label']} | {row['policy_label']} | "
            f"¥{row['energy_cost']:.0f} | {row['turbidity_reduction_pct']:.1f}% | "
            f"{row['stability']:.1%} | {row['balanced_score']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_static_png(
    frame: pd.DataFrame, output_path: Path, optimize: list[str], source_note: str
) -> None:
    try:
        import matplotlib.pyplot as plt

        render_matplotlib_png(frame, output_path, optimize, source_note, plt)
    except ModuleNotFoundError:
        render_pillow_png(frame, output_path, optimize, source_note)


def render_matplotlib_png(
    frame: pd.DataFrame,
    output_path: Path,
    optimize: list[str],
    source_note: str,
    plt: Any,
) -> None:
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [
        "Noto Sans CJK SC",
        "Microsoft YaHei",
        "SimHei",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "#f7f4ee"
    plt.rcParams["axes.facecolor"] = "#fffdf8"
    plt.rcParams["savefig.facecolor"] = "#f7f4ee"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    front = frame[frame["is_pareto"]]
    dominated = frame[~frame["is_pareto"]]
    selected = frame[frame["is_selected"]]
    envelope = pareto_envelope_2d(front)
    knee = front.sort_values("balanced_score", ascending=False).head(1)

    fig = plt.figure(figsize=(16, 9.5))
    gs = fig.add_gridspec(1, 2, width_ratios=[3.3, 1.05], wspace=0.12)
    ax = fig.add_subplot(gs[0, 0])
    side = fig.add_subplot(gs[0, 1])
    side.axis("off")

    if not dominated.empty:
        ax.scatter(
            dominated["energy_cost"],
            dominated["turbidity_reduction_pct"],
            s=56,
            facecolors="none",
            edgecolors="#8aa0ad",
            linewidths=1.1,
            alpha=0.62,
            label="被支配候选",
        )
    sc = ax.scatter(
        front["energy_cost"],
        front["turbidity_reduction_pct"],
        c=front["stability"],
        s=118,
        cmap="Spectral",
        edgecolors="#23313d",
        linewidths=0.9,
        label="帕累托非劣解",
        zorder=3,
    )
    if len(envelope) >= 2:
        ax.plot(
            envelope["energy_cost"],
            envelope["turbidity_reduction_pct"],
            color="#243b53",
            linewidth=2.4,
            alpha=0.82,
            label="二维前沿包络",
            zorder=2,
        )
    if not selected.empty:
        ax.scatter(
            selected["energy_cost"],
            selected["turbidity_reduction_pct"],
            marker="*",
            s=260,
            facecolors="#ffd166",
            edgecolors="#2b2d42",
            linewidths=1.4,
            label="当前多智能体策略",
            zorder=5,
        )
    if not knee.empty:
        row = knee.iloc[0]
        ax.scatter(
            [row["energy_cost"]],
            [row["turbidity_reduction_pct"]],
            marker="D",
            s=150,
            facecolors="#ef476f",
            edgecolors="white",
            linewidths=1.2,
            label="推荐折中点",
            zorder=6,
        )

    for _, row in selected.iterrows():
        ax.annotate(
            row["scenario_label"],
            (row["energy_cost"], row["turbidity_reduction_pct"]),
            xytext=(8, 8),
            textcoords="offset points",
            fontsize=9,
            color="#263238",
        )

    ax.set_title("帕累托前沿：成本-效果-稳定性权衡", fontsize=22, fontweight="bold", pad=18)
    ax.set_xlabel("治理成本 (¥/day)", fontsize=12)
    ax.set_ylabel("浊度削减率 (%)", fontsize=12)
    ax.grid(True, alpha=0.22, linewidth=0.8)
    ax.legend(loc="lower right", frameon=True, framealpha=0.92, fontsize=10)
    cbar = fig.colorbar(sc, ax=ax, pad=0.012)
    cbar.set_label("稳定度", fontsize=11)

    draw_matplotlib_side_panel(side, frame, optimize, source_note)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def draw_matplotlib_side_panel(
    side: Any, frame: pd.DataFrame, optimize: list[str], source_note: str
) -> None:
    front = frame[frame["is_pareto"]]
    selected = frame[frame["is_selected"]]
    knee = front.sort_values("balanced_score", ascending=False).head(1)

    side.text(0.0, 0.98, "图表读法", fontsize=16, fontweight="bold", va="top")
    side.text(
        0.0,
        0.89,
        "横轴越左成本越低，纵轴越高效果越好，颜色越偏暖代表稳定度越高。",
        fontsize=10.5,
        va="top",
        wrap=True,
        color="#334e68",
    )
    y = 0.74
    side.text(0.0, y, f"候选策略：{len(frame)}", fontsize=12, fontweight="bold")
    side.text(0.0, y - 0.06, f"非劣解：{len(front)}", fontsize=12, fontweight="bold")
    side.text(
        0.0,
        y - 0.12,
        f"当前策略在前沿：{int(selected['is_pareto'].sum())}/{len(selected)}",
        fontsize=12,
        fontweight="bold",
    )
    if not knee.empty:
        row = knee.iloc[0]
        side.text(0.0, 0.50, "推荐折中点", fontsize=14, fontweight="bold")
        side.text(
            0.0,
            0.43,
            (
                f"{row['scenario_label']} / {row['policy_label']}\n"
                f"成本 ¥{row['energy_cost']:.0f}/day\n"
                f"浊度削减 {row['turbidity_reduction_pct']:.1f}%\n"
                f"稳定度 {row['stability']:.1%}"
            ),
            fontsize=11,
            linespacing=1.55,
            color="#243b53",
        )
    side.text(0.0, 0.16, "优化目标", fontsize=13, fontweight="bold")
    side.text(0.0, 0.10, ", ".join(optimize), fontsize=10.5, color="#334e68")
    side.text(0.0, 0.04, source_note, fontsize=8.5, color="#627d98", wrap=True)


def render_pillow_png(
    frame: pd.DataFrame, output_path: Path, optimize: list[str], source_note: str
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    output_path.parent.mkdir(parents=True, exist_ok=True)

    width, height = 1800, 1120
    plot_left, plot_top = 150, 185
    plot_width, plot_height = 1180, 760
    side_left, side_top, side_width = 1390, 185, 330
    background = "#f7f4ee"
    panel = "#fffdf8"
    ink = "#243b53"

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    fonts = PillowFonts(ImageFont)

    draw.rounded_rectangle(
        [plot_left - 28, plot_top - 32, plot_left + plot_width + 28, plot_top + plot_height + 70],
        radius=18,
        fill=panel,
        outline="#e6dccd",
        width=2,
    )
    draw.rounded_rectangle(
        [side_left - 26, side_top - 32, side_left + side_width + 26, plot_top + plot_height + 70],
        radius=18,
        fill=panel,
        outline="#e6dccd",
        width=2,
    )

    title = "帕累托前沿：成本-效果-稳定性权衡"
    subtitle = (
        f"{len(frame)} 个候选策略，{int(frame['is_pareto'].sum())} 个非劣解；"
        "星标为当前多智能体策略，菱形为推荐折中点"
    )
    draw.text((80, 52), title, font=fonts.bold(46), fill=ink)
    draw.text((82, 114), subtitle, font=fonts.regular(22), fill="#52616b")

    x_max = nice_upper(frame["energy_cost"].max() * 1.06)
    y_max = nice_upper(frame["turbidity_reduction_pct"].max() * 1.16)
    x_ticks = nice_ticks(0.0, x_max, 6)
    y_ticks = nice_ticks(0.0, y_max, 6)

    def x_to_px(value: float) -> float:
        return plot_left + (float(value) / x_max) * plot_width if x_max > 0 else plot_left

    def y_to_px(value: float) -> float:
        return plot_top + plot_height - (float(value) / y_max) * plot_height if y_max > 0 else plot_top

    for tick in x_ticks:
        x = x_to_px(tick)
        draw.line([(x, plot_top), (x, plot_top + plot_height)], fill="#eadfce", width=1)
        label = f"{tick / 1000:.0f}k" if tick >= 1000 else f"{tick:.0f}"
        draw_centered_text(draw, (x, plot_top + plot_height + 22), label, fonts.regular(18), "#52616b")
    for tick in y_ticks:
        y = y_to_px(tick)
        draw.line([(plot_left, y), (plot_left + plot_width, y)], fill="#eadfce", width=1)
        draw_right_text(draw, (plot_left - 16, y - 10), f"{tick:.0f}", fonts.regular(18), "#52616b")

    draw.line([(plot_left, plot_top), (plot_left, plot_top + plot_height)], fill="#52616b", width=2)
    draw.line(
        [(plot_left, plot_top + plot_height), (plot_left + plot_width, plot_top + plot_height)],
        fill="#52616b",
        width=2,
    )
    draw_centered_text(
        draw,
        (plot_left + plot_width / 2, plot_top + plot_height + 58),
        "治理成本 (¥/day)",
        fonts.bold(22),
        ink,
    )
    draw_rotated_label(
        image,
        "浊度削减率 (%)",
        (40, plot_top + plot_height / 2 + 90),
        fonts.bold(22),
        ink,
    )

    front = frame[frame["is_pareto"]]
    dominated = frame[~frame["is_pareto"]]
    selected = frame[frame["is_selected"]]
    envelope = pareto_envelope_2d(front)

    if len(envelope) >= 2:
        line_points = [
            (x_to_px(row["energy_cost"]), y_to_px(row["turbidity_reduction_pct"]))
            for _, row in envelope.iterrows()
        ]
        draw.line(line_points, fill="#23313d", width=5, joint="curve")

    for _, row in dominated.iterrows():
        x, y = x_to_px(row["energy_cost"]), y_to_px(row["turbidity_reduction_pct"])
        draw.ellipse([x - 7, y - 7, x + 7, y + 7], outline="#8aa0ad", width=2)

    for _, row in front.iterrows():
        x, y = x_to_px(row["energy_cost"]), y_to_px(row["turbidity_reduction_pct"])
        color = stability_color(float(row["stability"]))
        draw.ellipse([x - 12, y - 12, x + 12, y + 12], fill=color, outline="#23313d", width=2)

    for _, row in selected.iterrows():
        x, y = x_to_px(row["energy_cost"]), y_to_px(row["turbidity_reduction_pct"])
        star_points = star_polygon(x, y, 22, 9)
        draw.polygon(star_points, fill="#ffd166", outline="#2b2d42")
        draw.line(star_points + [star_points[0]], fill="#2b2d42", width=2)
        label = str(row["scenario_label"])
        draw.text((x + 13, y - 28), label, font=fonts.regular(18), fill=ink)

    knee = front.sort_values("balanced_score", ascending=False).head(1)
    if not knee.empty:
        row = knee.iloc[0]
        x, y = x_to_px(row["energy_cost"]), y_to_px(row["turbidity_reduction_pct"])
        diamond = [(x, y - 18), (x + 18, y), (x, y + 18), (x - 18, y)]
        draw.polygon(diamond, fill="#ef476f", outline="white")
        draw.line(diamond + [diamond[0]], fill="white", width=2)

    draw_legend(draw, fonts, plot_left + plot_width - 365, plot_top + plot_height - 154)
    draw_side_panel(draw, fonts, frame, optimize, source_note, side_left, side_top, side_width)

    footer = (
        f"CSV: {relative_path(DEFAULT_FRONT_PATH)}  |  candidates: {relative_path(DEFAULT_CANDIDATES_PATH)}"
        f"  |  source: {source_note}"
    )
    draw.text((80, height - 48), footer, font=fonts.regular(17), fill="#627d98")
    image.save(output_path)


class PillowFonts:
    def __init__(self, image_font: Any) -> None:
        self.image_font = image_font
        self.regular_path = first_existing_font(
            [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        )
        self.bold_path = first_existing_font(
            [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ]
        )

    def regular(self, size: int) -> Any:
        return self._load(self.regular_path, size)

    def bold(self, size: int) -> Any:
        return self._load(self.bold_path, size)

    def _load(self, path: str | None, size: int) -> Any:
        if path:
            return self.image_font.truetype(path, size=size)
        return self.image_font.load_default()


def first_existing_font(paths: list[str]) -> str | None:
    for path in paths:
        if Path(path).exists():
            return path
    return None


def draw_side_panel(
    draw: Any,
    fonts: PillowFonts,
    frame: pd.DataFrame,
    optimize: list[str],
    source_note: str,
    x: int,
    y: int,
    width: int,
) -> None:
    front = frame[frame["is_pareto"]]
    selected = frame[frame["is_selected"]]
    knee = front.sort_values("balanced_score", ascending=False).head(1)

    draw.text((x, y), "关键结论", font=fonts.bold(30), fill="#243b53")
    lines = [
        ("候选策略", f"{len(frame)}"),
        ("非劣解", f"{len(front)}"),
        ("当前策略在前沿", f"{int(selected['is_pareto'].sum())}/{len(selected)}"),
    ]
    y_cursor = y + 58
    for label, value in lines:
        draw.text((x, y_cursor), label, font=fonts.regular(19), fill="#627d98")
        draw.text((x + width - 8, y_cursor - 4), value, font=fonts.bold(28), fill="#243b53", anchor="ra")
        y_cursor += 42

    if not knee.empty:
        row = knee.iloc[0]
        y_cursor += 10
        draw.rounded_rectangle([x, y_cursor, x + width, y_cursor + 154], radius=14, fill="#f4eadb")
        draw.text((x + 18, y_cursor + 14), "推荐折中点", font=fonts.bold(21), fill="#243b53")
        detail_lines = [
            f"{row['scenario_label']} / {row['policy_label']}",
            f"成本 ¥{row['energy_cost']:.0f}/day",
            f"浊度削减 {row['turbidity_reduction_pct']:.1f}%",
            f"稳定度 {row['stability']:.1%}",
        ]
        text_y = y_cursor + 48
        for line in detail_lines:
            draw.text((x + 18, text_y), line, font=fonts.regular(17), fill="#334e68")
            text_y += 25
        y_cursor += 176

    draw.text((x, y_cursor), "前沿 Top 5", font=fonts.bold(24), fill="#243b53")
    y_cursor += 38
    for _, row in front.sort_values("balanced_score", ascending=False).head(5).iterrows():
        label = f"{row['scenario_label']} {row['turbidity_reduction_pct']:.1f}%"
        detail = f"¥{row['energy_cost']:.0f}  {row['stability']:.0%}"
        draw.text((x, y_cursor), label, font=fonts.regular(16), fill="#243b53")
        draw.text((x, y_cursor + 22), detail, font=fonts.regular(14), fill="#627d98")
        y_cursor += 43

    y_cursor += 28
    draw_colorbar(draw, fonts, x, y_cursor)
    y_cursor += 70
    draw.text((x, y_cursor), "优化目标", font=fonts.bold(20), fill="#243b53")
    draw.text((x, y_cursor + 30), ", ".join(optimize), font=fonts.regular(16), fill="#627d98")


def draw_legend(draw: Any, fonts: PillowFonts, x: int, y: int) -> None:
    draw.rounded_rectangle([x - 18, y - 18, x + 340, y + 135], radius=14, fill="#fffaf0", outline="#e6dccd")
    items = [
        ("circle_open", "被支配候选"),
        ("circle", "帕累托非劣解"),
        ("star", "当前策略"),
        ("diamond", "推荐折中点"),
    ]
    for idx, (kind, label) in enumerate(items):
        item_y = y + idx * 35
        if kind == "circle_open":
            draw.ellipse([x, item_y, x + 18, item_y + 18], outline="#8aa0ad", width=2)
        elif kind == "circle":
            draw.ellipse([x, item_y, x + 18, item_y + 18], fill="#2f9c95", outline="#23313d", width=2)
        elif kind == "star":
            points = star_polygon(x + 9, item_y + 9, 13, 5)
            draw.polygon(points, fill="#ffd166", outline="#2b2d42")
        else:
            diamond = [(x + 9, item_y - 2), (x + 20, item_y + 9), (x + 9, item_y + 20), (x - 2, item_y + 9)]
            draw.polygon(diamond, fill="#ef476f", outline="white")
        draw.text((x + 34, item_y - 2), label, font=fonts.regular(18), fill="#243b53")


def draw_colorbar(draw: Any, fonts: PillowFonts, x: int, y: int) -> None:
    draw.text((x, y - 36), "稳定度色带", font=fonts.bold(20), fill="#243b53")
    width, height = 270, 18
    for i in range(width):
        value = i / max(width - 1, 1)
        draw.line([(x + i, y), (x + i, y + height)], fill=stability_color(value), width=1)
    draw.rectangle([x, y, x + width, y + height], outline="#52616b", width=1)
    draw.text((x, y + 26), "低", font=fonts.regular(15), fill="#627d98")
    draw.text((x + width - 18, y + 26), "高", font=fonts.regular(15), fill="#627d98")


def render_interactive_html(
    frame: pd.DataFrame, output_path: Path, optimize: list[str], source_note: str
) -> None:
    try:
        import plotly.graph_objects as go
    except ModuleNotFoundError:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    front = frame[frame["is_pareto"]]
    dominated = frame[~frame["is_pareto"]]
    selected = frame[frame["is_selected"]]
    envelope = pareto_envelope_2d(front)
    knee = front.sort_values("balanced_score", ascending=False).head(1)

    fig = go.Figure()
    hover_template = (
        "%{customdata[0]} / %{customdata[1]}<br>"
        "成本: ¥%{x:,.0f}/day<br>"
        "浊度削减: %{y:.1f}%<br>"
        "稳定度: %{marker.color:.1%}<br>"
        "放水: %{customdata[2]:.1f} m3/s<br>"
        "曝气: %{customdata[3]:.1f} kW<br>"
        "药剂: %{customdata[4]:.1f} kg/day<br>"
        "<extra></extra>"
    )
    if not dominated.empty:
        fig.add_trace(
            go.Scatter(
                x=dominated["energy_cost"],
                y=dominated["turbidity_reduction_pct"],
                mode="markers",
                name="被支配候选",
                marker={
                    "size": 8,
                    "color": dominated["stability"],
                    "colorscale": "Spectral",
                    "line": {"color": "#8aa0ad", "width": 1},
                    "symbol": "circle-open",
                    "opacity": 0.55,
                },
                customdata=hover_data(dominated),
                hovertemplate=hover_template,
            )
        )
    fig.add_trace(
        go.Scatter(
            x=front["energy_cost"],
            y=front["turbidity_reduction_pct"],
            mode="markers",
            name="帕累托非劣解",
            marker={
                "size": 12,
                "color": front["stability"],
                "colorscale": "Spectral",
                "showscale": True,
                "colorbar": {"title": "稳定度"},
                "line": {"color": "#23313d", "width": 1},
            },
            customdata=hover_data(front),
            hovertemplate=hover_template,
        )
    )
    if len(envelope) >= 2:
        fig.add_trace(
            go.Scatter(
                x=envelope["energy_cost"],
                y=envelope["turbidity_reduction_pct"],
                mode="lines",
                name="二维前沿包络",
                line={"color": "#243b53", "width": 3},
                hoverinfo="skip",
            )
        )
    if not selected.empty:
        fig.add_trace(
            go.Scatter(
                x=selected["energy_cost"],
                y=selected["turbidity_reduction_pct"],
                mode="markers+text",
                name="当前多智能体策略",
                text=selected["scenario_label"],
                textposition="top center",
                marker={
                    "size": 18,
                    "symbol": "star",
                    "color": "#ffd166",
                    "line": {"color": "#2b2d42", "width": 1},
                },
                customdata=hover_data(selected),
                hovertemplate=hover_template,
            )
        )
    if not knee.empty:
        fig.add_trace(
            go.Scatter(
                x=knee["energy_cost"],
                y=knee["turbidity_reduction_pct"],
                mode="markers",
                name="推荐折中点",
                marker={
                    "size": 16,
                    "symbol": "diamond",
                    "color": "#ef476f",
                    "line": {"color": "white", "width": 1},
                },
                customdata=hover_data(knee),
                hovertemplate=hover_template,
            )
        )

    fig.update_layout(
        title={
            "text": "WaterExpert 帕累托前沿：成本-效果-稳定性权衡",
            "x": 0.03,
            "xanchor": "left",
        },
        xaxis_title="治理成本 (¥/day)",
        yaxis_title="浊度削减率 (%)",
        template="plotly_white",
        height=780,
        margin={"l": 70, "r": 60, "t": 90, "b": 70},
        legend={"orientation": "h", "y": 1.06, "x": 0.42},
        annotations=[
            {
                "text": f"优化目标：{', '.join(optimize)}；数据来源：{source_note}",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.12,
                "showarrow": False,
                "font": {"size": 12, "color": "#52616b"},
                "align": "left",
            }
        ],
    )
    fig.write_html(output_path, include_plotlyjs=True)


def hover_data(frame: pd.DataFrame) -> np.ndarray:
    return frame[
        [
            "scenario_label",
            "policy_label",
            "release_rate",
            "aeration_intensity",
            "chemical_dosage",
        ]
    ].to_numpy()


def pareto_envelope_2d(front: pd.DataFrame) -> pd.DataFrame:
    if front.empty:
        return front
    ordered = front.sort_values(["energy_cost", "turbidity_reduction_pct"]).copy()
    keep_indices = []
    best_effect = -np.inf
    for index, row in ordered.iterrows():
        effect = float(row["turbidity_reduction_pct"])
        if effect > best_effect + 1e-9:
            keep_indices.append(index)
            best_effect = effect
    return ordered.loc[keep_indices].sort_values("energy_cost")


def clamp_float(value: Any, low: float, high: float) -> float:
    if not is_finite_number(value):
        return low
    return float(min(max(float(value), low), high))


def is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def nice_upper(value: float) -> float:
    if value <= 0 or not math.isfinite(value):
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    normalized = value / magnitude
    if normalized <= 1.2:
        nice = 1.2
    elif normalized <= 2:
        nice = 2
    elif normalized <= 3:
        nice = 3
    elif normalized <= 5:
        nice = 5
    else:
        nice = 10
    return nice * magnitude


def nice_ticks(start: float, stop: float, count: int) -> list[float]:
    if count <= 1:
        return [start, stop]
    return [start + (stop - start) * idx / (count - 1) for idx in range(count)]


def stability_color(value: float) -> str:
    value = float(min(max(value, 0.0), 1.0))
    stops = [
        (0.0, (178, 58, 72)),
        (0.5, (240, 195, 106)),
        (1.0, (47, 156, 149)),
    ]
    for (left_pos, left_color), (right_pos, right_color) in zip(stops, stops[1:]):
        if value <= right_pos:
            ratio = (value - left_pos) / (right_pos - left_pos)
            rgb = tuple(
                int(left_color[channel] + (right_color[channel] - left_color[channel]) * ratio)
                for channel in range(3)
            )
            return "#{:02x}{:02x}{:02x}".format(*rgb)
    return "#2f9c95"


def star_polygon(cx: float, cy: float, outer: float, inner: float) -> list[tuple[float, float]]:
    points = []
    for idx in range(10):
        radius = outer if idx % 2 == 0 else inner
        angle = -math.pi / 2 + idx * math.pi / 5
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def draw_centered_text(draw: Any, xy: tuple[float, float], text: str, font: Any, fill: str) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((xy[0] - (bbox[2] - bbox[0]) / 2, xy[1]), text, font=font, fill=fill)


def draw_right_text(draw: Any, xy: tuple[float, float], text: str, font: Any, fill: str) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((xy[0] - (bbox[2] - bbox[0]), xy[1]), text, font=font, fill=fill)


def draw_rotated_label(image: Any, text: str, xy: tuple[float, float], font: Any, fill: str) -> None:
    from PIL import Image, ImageDraw

    label = Image.new("RGBA", (340, 60), (255, 255, 255, 0))
    label_draw = ImageDraw.Draw(label)
    label_draw.text((0, 0), text, font=font, fill=fill)
    rotated = label.rotate(270, expand=True)
    image.paste(rotated, (int(xy[0]), int(xy[1] - rotated.height / 2)), rotated)


def wrap_text(text: str, width: int) -> str:
    words = text.replace("/", " / ").split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) > width and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return "\n".join(lines)


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
