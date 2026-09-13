from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from _quickstart_utils import (
    SCENARIO_LABELS,
    ensure_parent,
    load_many_scenarios,
    metric,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot a KPI radar chart from scenario outputs.")
    parser.add_argument("--scenarios", nargs="+", default=["1", "2", "3", "4"])
    parser.add_argument("--output", type=Path, default=Path("outputs/kpi_radar.png"))
    parser.add_argument("--scenario-dir", type=Path, default=Path("outputs/scenarios"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = load_many_scenarios(args.scenarios, args.scenario_dir)
    if not data:
        raise SystemExit(f"No scenario data found under {args.scenario_dir}")

    axes = ["Reduction", "Cost saving", "Stability", "Response", "Explainability"]
    angles = np.linspace(0, 2 * math.pi, len(axes), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7.2, 7.2), subplot_kw={"polar": True})
    for key, scenario_data in data.items():
        response_hours = metric(scenario_data, "avg_response_time_hours", 1.0)
        values = [
            metric(scenario_data, "avg_turbidity_reduction_ratio"),
            metric(scenario_data, "avg_cost_saving_ratio"),
            metric(scenario_data, "avg_stability"),
            max(0.0, min(1.0, 1.0 - response_hours / 4.0)),
            0.65 + 0.2 * bool(scenario_data.get("reasoning_viz_path")),
        ]
        values += values[:1]
        ax.plot(angles, values, linewidth=2, label=SCENARIO_LABELS.get(key, key))
        ax.fill(angles, values, alpha=0.08)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(axes)
    ax.set_ylim(0, 1.0)
    ax.set_title("WaterExpert KPI Radar")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1))
    fig.tight_layout()

    ensure_parent(args.output)
    fig.savefig(args.output, dpi=220, bbox_inches="tight")
    print(f"Saved KPI radar: {args.output}")


if __name__ == "__main__":
    main()
