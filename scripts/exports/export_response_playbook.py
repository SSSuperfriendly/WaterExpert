from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.interpretability.agent_exports import save_response_playbook


OUTPUT_DIR = PROJECT_ROOT / "outputs"
SCENARIO_TRIAGE_PATH = OUTPUT_DIR / "agent" / "scenario_triage.json"
THRESHOLD_KG_PATH = OUTPUT_DIR / "thresholds" / "mechanism_parameter_threshold_kg.json"
RESPONSE_PLAYBOOK_PATH = OUTPUT_DIR / "agent" / "response_playbook.json"
AGENT_CONTEXT_PATH = OUTPUT_DIR / "agent" / "agent_context.json"


def main() -> None:
    scenario_triage = json.loads(SCENARIO_TRIAGE_PATH.read_text(encoding="utf-8"))
    threshold_kg = json.loads(THRESHOLD_KG_PATH.read_text(encoding="utf-8"))
    output_path, playbook = save_response_playbook(
        output_path=RESPONSE_PLAYBOOK_PATH,
        scenario_triage=scenario_triage,
        threshold_kg=threshold_kg,
    )
    print(f"Saved response playbook: {output_path}")
    if AGENT_CONTEXT_PATH.exists():
        agent_context = json.loads(AGENT_CONTEXT_PATH.read_text(encoding="utf-8"))
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
        AGENT_CONTEXT_PATH.write_text(
            json.dumps(agent_context, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Updated agent context: {AGENT_CONTEXT_PATH}")


if __name__ == "__main__":
    main()
