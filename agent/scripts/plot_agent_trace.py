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
    parser = argparse.ArgumentParser(description="Plot an illustrative multi-agent trace for one episode.")
    parser.add_argument("--scenario", default="1")
    parser.add_argument("--episode", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("outputs/agent_trace_s1_ep5.png"))
    parser.add_argument("--scenario-dir", type=Path, default=Path("outputs/scenarios"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    key = scenario_key(args.scenario)
    data = load_scenario_data(key, args.scenario_dir)
    if not data:
        raise SystemExit(f"No scenario data found for {key}")

    episode = first_episode(data, args.episode - 1)
    safe_action = episode.get("safe_action", {})
    stages = [
        ("MSCIM", 0.0, 2.2),
        ("CMFBE", 2.0, 2.5),
        ("KB", 4.2, 1.1),
        ("AquaTurb-GPT", 5.2, 3.0),
        ("RL-TGRR", 8.2, 1.9),
        ("Safety", 10.0, 1.1),
    ]

    fig, ax = plt.subplots(figsize=(10, 4.8))
    for idx, (name, start, duration) in enumerate(stages):
        ax.broken_barh([(start, duration)], (idx - 0.35, 0.7), facecolors=f"C{idx}")
        ax.text(start + duration / 2, idx, name, ha="center", va="center", color="white", fontsize=9)

    ax.set_yticks(range(len(stages)))
    ax.set_yticklabels([stage[0] for stage in stages])
    ax.set_xlabel("Seconds")
    ax.set_title(f"Agent Trace - {key} episode {args.episode}")
    ax.grid(axis="x", alpha=0.25)
    ax.set_xlim(0, 12)
    text = (
        "Action: "
        f"release={safe_action.get('release_rate', 0):.2f}, "
        f"aeration={safe_action.get('aeration_intensity', 0):.2f}, "
        f"chemical={safe_action.get('chemical_dosage', 0):.2f}"
    )
    ax.text(0, -1.15, text, fontsize=9)
    fig.tight_layout()

    ensure_parent(args.output)
    fig.savefig(args.output, dpi=220, bbox_inches="tight")
    print(f"Saved agent trace: {args.output}")


if __name__ == "__main__":
    main()
