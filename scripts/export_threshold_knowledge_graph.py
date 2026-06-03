from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
import sys

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.interpretability.agent_exports import build_threshold_knowledge_graph


OUTPUT_DIR = PROJECT_ROOT / "outputs"
PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
SUMMARY_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_threshold_summary.csv"
CONTEXT_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_thresholds_by_context.csv"
OUTPUT_PATH = OUTPUT_DIR / "thresholds" / "mechanism_parameter_threshold_kg.json"


def main() -> None:
    predictions = pd.read_csv(PREDICTIONS_PATH)
    summary_df = pd.read_csv(SUMMARY_PATH)
    context_df = pd.read_csv(CONTEXT_PATH)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            build_threshold_knowledge_graph(predictions, summary_df, context_df),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved threshold knowledge graph: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
