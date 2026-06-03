from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.interpretability.agent_exports import (
    save_agent_context,
    save_response_playbook,
    save_scenario_triage,
)


OUTPUT_DIR = PROJECT_ROOT / "outputs"
METRICS_PATH = OUTPUT_DIR / "metrics" / "metrics.json"
BEST_MODEL_PATH = OUTPUT_DIR / "metrics" / "best_model_summary.json"
THRESHOLD_KG_PATH = OUTPUT_DIR / "thresholds" / "mechanism_parameter_threshold_kg.json"
THRESHOLD_SUMMARY_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_threshold_summary.csv"
PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
FEATURES_PATH = OUTPUT_DIR / "intermediate" / "multimodal_daily_dataset.csv"
AGENT_CONTEXT_PATH = OUTPUT_DIR / "agent" / "agent_context.json"
SCENARIO_TRIAGE_JSON_PATH = OUTPUT_DIR / "agent" / "scenario_triage.json"
SCENARIO_TRIAGE_CSV_PATH = OUTPUT_DIR / "diagnosis" / "scenario_triage_daily.csv"
RESPONSE_PLAYBOOK_PATH = OUTPUT_DIR / "agent" / "response_playbook.json"
MECHANISM_DIGEST_PATH = OUTPUT_DIR / "agent" / "cmfbe_mechanism_intervention_digest.json"


def main() -> None:
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    best_model_summary = json.loads(BEST_MODEL_PATH.read_text(encoding="utf-8"))
    threshold_kg = json.loads(THRESHOLD_KG_PATH.read_text(encoding="utf-8"))
    scenario_triage = None
    response_playbook = None
    mechanism_digest = None
    if (
        THRESHOLD_SUMMARY_PATH.exists()
        and PREDICTIONS_PATH.exists()
        and FEATURES_PATH.exists()
    ):
        _, _, scenario_triage = save_scenario_triage(
            output_json_path=SCENARIO_TRIAGE_JSON_PATH,
            output_csv_path=SCENARIO_TRIAGE_CSV_PATH,
            predictions=pd.read_csv(PREDICTIONS_PATH),
            features=pd.read_csv(FEATURES_PATH),
            threshold_summary=pd.read_csv(THRESHOLD_SUMMARY_PATH),
        )
    if scenario_triage is not None:
        _, response_playbook = save_response_playbook(
            output_path=RESPONSE_PLAYBOOK_PATH,
            scenario_triage=scenario_triage,
            threshold_kg=threshold_kg,
        )
    if MECHANISM_DIGEST_PATH.exists():
        mechanism_digest = json.loads(MECHANISM_DIGEST_PATH.read_text(encoding="utf-8"))
    save_agent_context(
        output_path=AGENT_CONTEXT_PATH,
        metrics=metrics,
        best_model_summary=best_model_summary,
        threshold_kg=threshold_kg,
        scenario_triage=scenario_triage,
        response_playbook=response_playbook,
        mechanism_digest=mechanism_digest,
    )
    print(f"Saved agent context: {AGENT_CONTEXT_PATH}")


if __name__ == "__main__":
    main()
