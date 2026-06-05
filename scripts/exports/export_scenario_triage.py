from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.interpretability.agent_exports import save_scenario_triage


OUTPUT_DIR = PROJECT_ROOT / "outputs"
PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
FEATURES_PATH = OUTPUT_DIR / "intermediate" / "multimodal_daily_dataset.csv"
THRESHOLD_SUMMARY_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_threshold_summary.csv"
SCENARIO_JSON_PATH = OUTPUT_DIR / "agent" / "scenario_triage.json"
SCENARIO_CSV_PATH = OUTPUT_DIR / "diagnosis" / "scenario_triage_daily.csv"
AGENT_CONTEXT_PATH = OUTPUT_DIR / "agent" / "agent_context.json"


def main() -> None:
    predictions = pd.read_csv(PREDICTIONS_PATH)
    features = pd.read_csv(FEATURES_PATH)
    threshold_summary = pd.read_csv(THRESHOLD_SUMMARY_PATH)
    output_json_path, output_csv_path, summary = save_scenario_triage(
        output_json_path=SCENARIO_JSON_PATH,
        output_csv_path=SCENARIO_CSV_PATH,
        predictions=predictions,
        features=features,
        threshold_summary=threshold_summary,
    )
    print(f"Saved scenario triage json: {output_json_path}")
    print(f"Saved scenario triage csv: {output_csv_path}")
    if AGENT_CONTEXT_PATH.exists():
        agent_context = json.loads(AGENT_CONTEXT_PATH.read_text(encoding="utf-8"))
        agent_context["scenario_triage_path"] = "outputs/agent/scenario_triage.json"
        agent_context["scenario_counts"] = summary.get("scenario_counts", {})
        agent_context["scenario_high_priority_days"] = summary.get("high_priority_days", [])
        AGENT_CONTEXT_PATH.write_text(
            json.dumps(agent_context, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Updated agent context: {AGENT_CONTEXT_PATH}")


if __name__ == "__main__":
    main()
