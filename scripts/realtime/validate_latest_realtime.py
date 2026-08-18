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
        default=str(PROJECT_ROOT / "configs" / "default.yaml"),
        help="Path to the WaterExpert runtime config.",
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
    parser.add_argument(
        "--section-name",
        default="吴淞口",
        help="Target section name to validate.",
    )
    parser.add_argument(
        "--as-of-time",
        default=None,
        help="Optional realtime snapshot time, for example '2026-07-05 13:00:00'.",
    )
    parser.add_argument(
        "--check-section",
        default=None,
        help="Additional station section name to check for catalog/realtime availability.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = generate_latest_realtime_validation(
        LatestValidationConfig(
            config_path=Path(args.config).resolve(),
            outputs_root=Path(args.outputs_root).resolve(),
            artifact_root=Path(args.artifact_root).resolve(),
            section_name=args.section_name,
            as_of_time=args.as_of_time,
            check_section_name=args.check_section,
        )
    )
    print("Latest realtime validation complete.")
    print(f"Station: {result['target_section']}")
    print(f"Monitor time: {result['latest_observation']['monitor_time']}")
    print(
        f"{result['summary_metrics']['prediction_success_rate_title']}: "
        f"{result['summary_metrics']['prediction_success_rate_label']}"
    )
    print(f"Historical similar day: {result['summary_metrics']['historical_similar_day']}")
    check = result.get("station_access_checks", {}).get(args.check_section)
    if check:
        print(f"{args.check_section} access status: {check['status']}")


if __name__ == "__main__":
    main()
