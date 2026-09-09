from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect local AquaTurb-GPT training examples from scenario outputs.")
    parser.add_argument("--scenario-dir", type=Path, default=Path("outputs/scenarios"))
    parser.add_argument("--output", type=Path, default=Path("outputs/agents/aquaturb_gpt_traces/training_data.jsonl"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with args.output.open("w", encoding="utf-8") as out:
        for path in sorted(args.scenario_dir.glob("s*/data.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for episode in data.get("episodes", []):
                planning = episode.get("planning", {})
                strategy = planning.get("strategy", {})
                if not strategy:
                    continue
                sample = {
                    "scenario": episode.get("scenario", path.parent.name),
                    "input": {
                        "state": episode.get("feedback", {}).get("state", {}),
                        "diagnosis": episode.get("diagnosis", {}),
                    },
                    "output": strategy,
                    "backend": planning.get("backend_used"),
                }
                out.write(json.dumps(sample, ensure_ascii=False, default=str) + "\n")
                count += 1
    print(f"Saved {count} training samples to {args.output}")


if __name__ == "__main__":
    main()
