from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {
    "water": {"date", "station_code", "turbidity"},
    "weather": {"Year", "Mon", "Day"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local WaterExpert input CSV files.")
    parser.add_argument(
        "--water",
        type=Path,
        default=Path("data/full_station_database/water_quality_daily_all_stations.csv"),
    )
    parser.add_argument("--weather", type=Path, default=Path("data/raw/shanghai_weather_daily.csv"))
    return parser.parse_args()


def validate_csv(path: Path, required: set[str], label: str) -> bool:
    if not path.exists():
        print(f"[FAIL] {label}: missing {path}")
        return False
    frame = pd.read_csv(path, nrows=10)
    missing = sorted(required - set(frame.columns))
    if missing:
        print(f"[FAIL] {label}: missing columns {missing}")
        return False
    print(f"[OK] {label}: {path} has required columns")
    return True


def main() -> None:
    args = parse_args()
    ok = True
    ok &= validate_csv(args.water, REQUIRED_COLUMNS["water"], "water quality")
    ok &= validate_csv(args.weather, REQUIRED_COLUMNS["weather"], "weather")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
