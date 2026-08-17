from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.cross_modal import DEFAULT_OUTPUT_DIR, evaluate_and_write

DEFAULT_INPUT = DEFAULT_OUTPUT_DIR / "zhangjiabang_cross_modal_daily.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Zhangjiabang model performance before and after cross-modal UAV features."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = evaluate_and_write(args.input, args.output_dir)
    print(f"Evaluated samples: {summary['sample_count']}")
    for target, payload in summary["targets"].items():
        print(
            f"{target}: best={payload['best_model']} "
            f"rmse={payload['best_rmse']:.4f} "
            f"success_rate={payload['best_success_rate']:.2%}"
        )
    print(f"Summary: {summary['outputs']['summary_json']}")


if __name__ == "__main__":
    main()
