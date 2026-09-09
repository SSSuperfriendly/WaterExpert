from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from _quickstart_utils import SCENARIO_LABELS, ensure_parent, load_many_scenarios, metric


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a compact PDF report from local WaterExpert outputs.")
    parser.add_argument("--scenarios", nargs="+", default=["1", "2", "3", "4"])
    parser.add_argument("--include-reasoning", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("final_presentation.pdf"))
    parser.add_argument("--scenario-dir", type=Path, default=Path("outputs/scenarios"))
    return parser.parse_args()


def add_text_page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig, ax = plt.subplots(figsize=(8.27, 11.69))
    ax.axis("off")
    ax.text(0.06, 0.95, title, fontsize=18, fontweight="bold", va="top")
    ax.text(0.06, 0.89, "\n".join(lines), fontsize=10, va="top", family="monospace")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    data = load_many_scenarios(args.scenarios, args.scenario_dir)
    if not data:
        raise SystemExit(f"No scenario data found under {args.scenario_dir}")

    ensure_parent(args.output)
    rows = []
    for key, scenario_data in data.items():
        rows.append(
            (
                SCENARIO_LABELS.get(key, key),
                metric(scenario_data, "avg_turbidity_reduction_ratio") * 100,
                metric(scenario_data, "avg_cost_saving_ratio") * 100,
                metric(scenario_data, "avg_stability") * 100,
                metric(scenario_data, "avg_response_time_hours", 1.0),
            )
        )

    with PdfPages(args.output) as pdf:
        add_text_page(
            pdf,
            "WaterExpert Multi-Agent Evaluation",
            [
                "Scenario                 Reduction  CostSave  Stability  Response(h)",
                "-" * 68,
                *[
                    f"{name:<24} {red:>8.1f}% {save:>8.1f}% {stab:>9.1f}% {resp:>10.2f}"
                    for name, red, save, stab, resp in rows
                ],
            ],
        )

        fig, ax = plt.subplots(figsize=(8.27, 5.4))
        names = [row[0] for row in rows]
        reductions = [row[1] for row in rows]
        savings = [row[2] for row in rows]
        ax.plot(names, reductions, marker="o", label="Reduction")
        ax.plot(names, savings, marker="o", label="Cost saving")
        ax.axhline(30, color="#777777", linestyle="--", linewidth=1, label="30% target")
        ax.set_ylabel("Percent")
        ax.set_title("Cross-scenario KPI Summary")
        ax.tick_params(axis="x", rotation=15)
        ax.grid(axis="y", alpha=0.25)
        ax.legend()
        fig.tight_layout()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        if args.include_reasoning:
            reasoning_lines = []
            for key, scenario_data in data.items():
                reasoning_lines.append(
                    f"{SCENARIO_LABELS.get(key, key)} reasoning artifact: "
                    f"{scenario_data.get('reasoning_viz_path') or 'not generated locally'}"
                )
            add_text_page(pdf, "Reasoning Artifacts", reasoning_lines)

    print(f"Saved PDF report: {args.output}")


if __name__ == "__main__":
    main()
