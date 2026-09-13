from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from _quickstart_utils import (
    ensure_parent,
    first_episode,
    load_scenario_data,
    scenario_key,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a compact LLM planning trace from scenario output.")
    parser.add_argument("--scenario", default="1")
    parser.add_argument("--output", type=Path, default=Path("outputs/llm_reasoning_s1.png"))
    parser.add_argument("--scenario-dir", type=Path, default=Path("outputs/scenarios"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    key = scenario_key(args.scenario)
    data = load_scenario_data(key, args.scenario_dir)
    if not data:
        raise SystemExit(f"No scenario data found for {key}")

    episode = first_episode(data)
    planning = episode.get("planning", {})
    strategy = planning.get("strategy", {})
    state = episode.get("feedback", {}).get("state", {})
    actions = strategy.get("recommended_actions", [])
    action_text = ", ".join(
        f"{item.get('action')}@{float(item.get('intensity', 0)):.2f}" for item in actions
    ) or "fallback action"

    boxes = [
        f"Input\nTurbidity: {state.get('turbidity', 'n/a')}\nRainfall 3d: {state.get('rainfall_3d', 'n/a')}",
        f"Scenario\n{planning.get('scenario_detected', key)}",
        f"Weights\n{strategy.get('objective_weights', {})}",
        f"Action\n{action_text}",
        f"Backend\n{planning.get('backend_used', 'unknown')}",
    ]

    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.axis("off")
    for idx, text in enumerate(boxes):
        x = 0.04 + idx * 0.19
        ax.text(
            x,
            0.55,
            text,
            ha="center",
            va="center",
            bbox={"boxstyle": "round,pad=0.45", "facecolor": f"C{idx}", "alpha": 0.14},
            fontsize=9,
        )
        if idx < len(boxes) - 1:
            ax.annotate("", xy=(x + 0.105, 0.55), xytext=(x + 0.075, 0.55), arrowprops={"arrowstyle": "->"})
    ax.set_title("AquaTurb-GPT Planning Trace")
    fig.tight_layout()

    ensure_parent(args.output)
    fig.savefig(args.output, dpi=220, bbox_inches="tight")
    print(f"Saved LLM reasoning trace: {args.output}")


if __name__ == "__main__":
    main()
