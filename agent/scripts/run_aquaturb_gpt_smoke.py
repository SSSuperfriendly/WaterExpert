from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.agents.aquaturb_gpt_agent import AquaTurbGPTAgent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test the AquaTurb-GPT planning agent.")
    parser.add_argument(
        "--backend",
        choices=["api", "local"],
        default="api",
        help="DeepSeek backend to request. API mode falls back when no key/network is available.",
    )
    parser.add_argument(
        "--scenario",
        default="s1_external_input",
        help="Scenario key used in the smoke-test planning input.",
    )
    return parser.parse_args()


def build_planning_input(scenario: str) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "state": {
            "date": "2025-10-31",
            "turbidity": 25.5,
            "flow_rate": 28.5,
            "rainfall_3d": 45.3,
            "rainfall_7d": 120.5,
            "chlorophyll_a": 5.2,
        },
        "diagnosis": {
            "primary_drivers": "external rainfall and suspended sediment input",
            "confidence": 0.82,
            "flow_condition": "high",
            "turbidity": 25.5,
        },
    }


def main() -> None:
    args = parse_args()
    if args.backend == "api" and not os.getenv("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY is not set; API backend will use the built-in fallback strategy.")

    agent = AquaTurbGPTAgent(config={"deepseek": {"backend": args.backend}})
    result = agent.act(build_planning_input(args.scenario))
    print("AquaTurb-GPT smoke test:")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
