from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from _quickstart_utils import SCENARIO_LABELS, ensure_parent, load_many_scenarios, metric


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot scenario-level KPI comparison.")
    parser.add_argument("--scenarios", nargs="+", default=["1", "2", "3", "4"])
    parser.add_argument("--output", type=Path, default=Path("outputs/comparison_scenarios.png"))
    parser.add_argument("--scenario-dir", type=Path, default=Path("outputs/scenarios"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = load_many_scenarios(args.scenarios, args.scenario_dir)
    if not data:
        raise SystemExit(f"No scenario data found under {args.scenario_dir}")

    keys = list(data)
    labels = [SCENARIO_LABELS.get(key, key) for key in keys]
    x = np.arange(len(keys))
    width = 0.25

    reduction = [metric(data[key], "avg_turbidity_reduction_ratio") * 100 for key in keys]
    saving = [metric(data[key], "avg_cost_saving_ratio") * 100 for key in keys]
    stability = [metric(data[key], "avg_stability") * 100 for key in keys]

    fig, ax = plt.subplots(figsize=(11, 5.8))
    ax.bar(x - width, reduction, width, label="Turbidity reduction")
    ax.bar(x, saving, width, label="Cost saving")
    ax.bar(x + width, stability, width, label="Stability")
    ax.axhline(30, color="#555555", linewidth=1, linestyle="--", label="30% target")
    ax.set_ylabel("Percent")
    ax.set_title("WaterExpert Scenario KPI Comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylim(0, max(105, max(stability + reduction + saving) * 1.15))
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="upper left", ncols=2)
    fig.tight_layout()

    ensure_parent(args.output)
    fig.savefig(args.output, dpi=220, bbox_inches="tight")
    print(f"Saved scenario comparison: {args.output}")


if __name__ == "__main__":
    main()
