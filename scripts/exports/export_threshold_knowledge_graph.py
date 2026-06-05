from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export threshold knowledge graph artifacts."
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default=str(OUTPUT_DIR),
        help="Artifact output root. Defaults to repository outputs/.",
    )
    return parser.parse_args()


def configure_output_root(output_root: Path) -> None:
    global OUTPUT_DIR
    global PREDICTIONS_PATH
    global SUMMARY_PATH
    global CONTEXT_PATH
    global OUTPUT_PATH

    OUTPUT_DIR = output_root.resolve()
    PREDICTIONS_PATH = OUTPUT_DIR / "predictions" / "predictions.csv"
    SUMMARY_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_threshold_summary.csv"
    CONTEXT_PATH = OUTPUT_DIR / "thresholds" / "cmfbe_thresholds_by_context.csv"
    OUTPUT_PATH = OUTPUT_DIR / "thresholds" / "mechanism_parameter_threshold_kg.json"


def main() -> None:
    args = parse_args()
    configure_output_root(Path(args.output_root))
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
