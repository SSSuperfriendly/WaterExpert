from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.interpretability.agent_exports import save_scenario_triage
from water_ai.utils.io import save_json


@dataclass(frozen=True)
class TriageArtifacts:
    output_root: Path
    predictions_path: Path
    features_path: Path
    threshold_summary_path: Path
    scenario_json_path: Path
    scenario_csv_path: Path
    agent_context_path: Path

    @classmethod
    def from_output_root(cls, output_root: Path) -> "TriageArtifacts":
        resolved_root = output_root.resolve()
        return cls(
            output_root=resolved_root,
            predictions_path=resolved_root / "predictions" / "predictions.csv",
            features_path=resolved_root / "intermediate" / "multimodal_daily_dataset.csv",
            threshold_summary_path=resolved_root / "thresholds" / "cmfbe_threshold_summary.csv",
            scenario_json_path=resolved_root / "agent" / "scenario_triage.json",
            scenario_csv_path=resolved_root / "diagnosis" / "scenario_triage_daily.csv",
            agent_context_path=resolved_root / "agent" / "agent_context.json",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export scenario triage artifacts.")
    parser.add_argument(
        "--output-root",
        type=str,
        default=str(PROJECT_ROOT / "outputs"),
        help="Artifact output root. Defaults to repository outputs/.",
    )
    return parser.parse_args()


def update_agent_context(artifacts: TriageArtifacts, summary: dict[str, object]) -> None:
    if not artifacts.agent_context_path.exists():
        return
    agent_context = json.loads(artifacts.agent_context_path.read_text(encoding="utf-8"))
    agent_context["scenario_triage_path"] = "outputs/agent/scenario_triage.json"
    agent_context["scenario_counts"] = summary.get("scenario_counts", {})
    agent_context["scenario_high_priority_days"] = summary.get("high_priority_days", [])
    save_json(agent_context, artifacts.agent_context_path)
    print(f"Updated agent context: {artifacts.agent_context_path}")


def main() -> None:
    args = parse_args()
    artifacts = TriageArtifacts.from_output_root(Path(args.output_root))
    output_json_path, output_csv_path, summary = save_scenario_triage(
        output_json_path=artifacts.scenario_json_path,
        output_csv_path=artifacts.scenario_csv_path,
        predictions=pd.read_csv(artifacts.predictions_path),
        features=pd.read_csv(artifacts.features_path),
        threshold_summary=pd.read_csv(artifacts.threshold_summary_path),
    )
    print(f"Saved scenario triage json: {output_json_path}")
    print(f"Saved scenario triage csv: {output_csv_path}")
    update_agent_context(artifacts, summary)


if __name__ == "__main__":
    main()
