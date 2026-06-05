from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.interpretability.agent_exports import save_response_playbook
from water_ai.utils.io import save_json


@dataclass(frozen=True)
class PlaybookArtifacts:
    output_root: Path
    scenario_triage_path: Path
    threshold_kg_path: Path
    response_playbook_path: Path
    agent_context_path: Path

    @classmethod
    def from_output_root(cls, output_root: Path) -> "PlaybookArtifacts":
        resolved_root = output_root.resolve()
        return cls(
            output_root=resolved_root,
            scenario_triage_path=resolved_root / "agent" / "scenario_triage.json",
            threshold_kg_path=resolved_root / "thresholds" / "mechanism_parameter_threshold_kg.json",
            response_playbook_path=resolved_root / "agent" / "response_playbook.json",
            agent_context_path=resolved_root / "agent" / "agent_context.json",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export response playbook artifacts.")
    parser.add_argument(
        "--output-root",
        type=str,
        default=str(PROJECT_ROOT / "outputs"),
        help="Artifact output root. Defaults to repository outputs/.",
    )
    return parser.parse_args()


def update_agent_context(artifacts: PlaybookArtifacts) -> None:
    if not artifacts.agent_context_path.exists():
        return
    agent_context = json.loads(artifacts.agent_context_path.read_text(encoding="utf-8"))
    agent_context["response_playbook_path"] = "outputs/agent/response_playbook.json"
    agent_context["recommended_agent_queries"] = list(
        dict.fromkeys(
            [
                *agent_context.get("recommended_agent_queries", []),
                "What follow-up monitoring actions fit the current empirical scenario?",
                "Which guarded response template matches the latest high-priority case?",
            ]
        )
    )
    save_json(agent_context, artifacts.agent_context_path)
    print(f"Updated agent context: {artifacts.agent_context_path}")


def main() -> None:
    args = parse_args()
    artifacts = PlaybookArtifacts.from_output_root(Path(args.output_root))
    output_path, _ = save_response_playbook(
        output_path=artifacts.response_playbook_path,
        scenario_triage=json.loads(artifacts.scenario_triage_path.read_text(encoding="utf-8")),
        threshold_kg=json.loads(artifacts.threshold_kg_path.read_text(encoding="utf-8")),
    )
    print(f"Saved response playbook: {output_path}")
    update_agent_context(artifacts)


if __name__ == "__main__":
    main()
