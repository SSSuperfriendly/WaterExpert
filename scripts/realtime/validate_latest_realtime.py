from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.realtime.latest_validation import (
    LatestValidationConfig,
    generate_latest_realtime_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate latest national surface-water realtime data against WaterExpert models.")
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "configs" / "prototype_repo.yaml"),
        help="Path to the WaterExpert runtime config.",
    )
    parser.add_argument(
        "--draft",
        default=str(PROJECT_ROOT / "docs" / "API" / "draft.txt"),
        help="Path to the aliyun API draft file containing AppCode.",
    )
    parser.add_argument(
        "--outputs-root",
        default=str(PROJECT_ROOT / "outputs"),
        help="Path to historical outputs root.",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(PROJECT_ROOT / "var" / "realtime"),
        help="Directory for latest realtime validation artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = generate_latest_realtime_validation(
        LatestValidationConfig(
            config_path=Path(args.config).resolve(),
            draft_path=Path(args.draft).resolve(),
            outputs_root=Path(args.outputs_root).resolve(),
            artifact_root=Path(args.artifact_root).resolve(),
        )
    )
    print("Latest realtime validation complete.")
    print(f"Station: {result['target_section']}")
    print(f"Monitor time: {result['latest_observation']['monitor_time']}")
    print(f"Prediction success rate: {result['summary_metrics']['prediction_success_rate_label']}")
    print(f"Historical similar day: {result['summary_metrics']['historical_similar_day']}")


if __name__ == "__main__":
    main()
