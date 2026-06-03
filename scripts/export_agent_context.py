from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.interpretability.agent_exports import save_agent_context


OUTPUT_DIR = PROJECT_ROOT / "outputs"
METRICS_PATH = OUTPUT_DIR / "metrics" / "metrics.json"
BEST_MODEL_PATH = OUTPUT_DIR / "metrics" / "best_model_summary.json"
THRESHOLD_KG_PATH = OUTPUT_DIR / "thresholds" / "mechanism_parameter_threshold_kg.json"
AGENT_CONTEXT_PATH = OUTPUT_DIR / "agent" / "agent_context.json"


def main() -> None:
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    best_model_summary = json.loads(BEST_MODEL_PATH.read_text(encoding="utf-8"))
    threshold_kg = json.loads(THRESHOLD_KG_PATH.read_text(encoding="utf-8"))
    save_agent_context(
        output_path=AGENT_CONTEXT_PATH,
        metrics=metrics,
        best_model_summary=best_model_summary,
        threshold_kg=threshold_kg,
    )
    print(f"Saved agent context: {AGENT_CONTEXT_PATH}")


if __name__ == "__main__":
    main()
