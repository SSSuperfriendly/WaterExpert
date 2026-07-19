from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WATER_QUALITY_PATH = (
    PROJECT_ROOT
    / "data"
    / "full_station_database"
    / "water_quality_daily_all_stations_with_secchi.csv"
)
DEFAULT_WEATHER_PATH = PROJECT_ROOT / "data" / "raw" / "shanghai_weather_daily.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "proxy" / "zhangjiabang_proxy"

WEATHER_FIELD_MAP = {
    "\u6c14\u538b": "weather_pressure",
    "\u5e73\u5747\u6c14\u6e29": "weather_air_temp",
    "\u76f8\u5bf9\u6e7f\u5ea6": "weather_humidity",
    "\u5f53\u5929\u964d\u6c34\u91cf": "weather_precipitation",
    "\u5e73\u5747\u98ce\u901f": "weather_wind_speed",
    "\u5e73\u5747\u98ce\u5411": "weather_wind_dir",
}
WATER_FIELDS = (
    "water_temp",
    "ph",
    "dissolved_oxygen",
    "conductivity",
    "turbidity",
    "codmn",
    "nh3_n",
    "toc",
    "tp",
    "tn",
    "chlorophyll_a",
    "algae_density",
    "water_quality_class",
    "station_status",
    "secchi_depth_sd_m",
    "secchi_formula",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a daily proxy dataset for Zhangjiabang East Gate using a nearby "
            "water-quality station and a specified weather station."
        )
    )
    parser.add_argument(
        "--target-site",
        default="\u5f20\u5bb6\u6d5c\u4e1c\u95f8\u7ad9",
        help="Human-readable target site name.",
    )
    parser.add_argument(
        "--water-station-code",
        default="2198",
        help="Proxy water-quality station code. Default: 2198.",
    )
    parser.add_argument(
        "--weather-station-id",
        default="58370",
        help="Proxy weather station id. Default: 58370.",
    )
    parser.add_argument(
        "--water-quality-path",
        type=Path,
        default=DEFAULT_WATER_QUALITY_PATH,
        help="Processed all-station water-quality CSV.",
    )
    parser.add_argument(
        "--weather-path",
        type=Path,
        default=DEFAULT_WEATHER_PATH,
        help="Shanghai daily weather CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the generated proxy CSV and summary JSON.",
    )
    return parser.parse_args()


def _haversine_km(
    lat_a: float | None,
    lon_a: float | None,
    lat_b: float | None,
    lon_b: float | None,
) -> float | None:
    if None in (lat_a, lon_a, lat_b, lon_b):
        return None
    radius_km = 6371.0088
    phi_a = math.radians(float(lat_a))
    phi_b = math.radians(float(lat_b))
    d_phi = math.radians(float(lat_b) - float(lat_a))
    d_lambda = math.radians(float(lon_b) - float(lon_a))
    hav = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(hav))


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def _date_range(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {"start": "", "end": ""}
    return {
        "start": frame["date"].min().strftime("%Y-%m-%d"),
        "end": frame["date"].max().strftime("%Y-%m-%d"),
    }


def _missing_summary(frame: pd.DataFrame, fields: list[str]) -> list[dict[str, Any]]:
    total_rows = len(frame)
    summary: list[dict[str, Any]] = []
    for field in fields:
        missing_count = int(frame[field].isna().sum()) if field in frame else total_rows
        summary.append(
            {
                "field": field,
                "missing_count": missing_count,
                "missing_rate": (missing_count / total_rows) if total_rows else None,
            }
        )
    return summary


def _first_value(frame: pd.DataFrame, field: str) -> Any:
    if frame.empty or field not in frame:
        return None
    values = frame[field].dropna()
    if values.empty:
        return None
    value = values.iloc[0]
    return value.item() if hasattr(value, "item") else value


def build_proxy_dataset(
    *,
    target_site: str,
    water_station_code: str,
    weather_station_id: str,
    water_quality_path: Path,
    weather_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    water_quality = pd.read_csv(water_quality_path, encoding="utf-8-sig", parse_dates=["date"])
    weather = pd.read_csv(weather_path, encoding="utf-8-sig")
    weather["date"] = pd.to_datetime(
        weather[["Year", "Mon", "Day"]].rename(
            columns={"Year": "year", "Mon": "month", "Day": "day"}
        )
    )

    water_rows = water_quality[
        water_quality["station_code"].astype(str) == str(water_station_code)
    ].copy()
    weather_rows = weather[weather["Station_Id_C"].astype(str) == str(weather_station_id)].copy()
    if water_rows.empty:
        raise ValueError(f"No water-quality rows found for station_code={water_station_code}")
    if weather_rows.empty:
        raise ValueError(f"No weather rows found for Station_Id_C={weather_station_id}")

    weather_rows = weather_rows.rename(
        columns={
            "Station_Id_C": "weather_station_id",
            "Lat": "weather_latitude",
            "Lon": "weather_longitude",
            "Alti": "weather_altitude",
            "City": "weather_city",
            "Station_Name": "weather_station_name",
            "Cnty": "weather_district",
            "Province": "weather_province",
            **WEATHER_FIELD_MAP,
        }
    )

    water_columns = [
        "date",
        "station_code",
        "station_name",
        "province",
        "city",
        "basin",
        "river",
        "longitude",
        "latitude",
        *WATER_FIELDS,
        "source_file",
    ]
    weather_columns = [
        "date",
        "weather_station_id",
        "weather_station_name",
        "weather_district",
        "weather_city",
        "weather_province",
        "weather_longitude",
        "weather_latitude",
        "weather_altitude",
        *WEATHER_FIELD_MAP.values(),
    ]
    merged = water_rows[water_columns].merge(
        weather_rows[weather_columns],
        on="date",
        how="inner",
    )
    merged.insert(1, "target_site", target_site)
    merged.insert(2, "proxy_status", "substitute_not_direct_measurement")
    merged = merged.rename(
        columns={
            "station_code": "water_quality_proxy_station_code",
            "station_name": "water_quality_proxy_station_name",
            "province": "water_quality_proxy_province",
            "city": "water_quality_proxy_city",
            "basin": "water_quality_proxy_basin",
            "river": "water_quality_proxy_river",
            "longitude": "water_quality_proxy_longitude",
            "latitude": "water_quality_proxy_latitude",
            "source_file": "water_quality_source_file",
        }
    )

    water_lat = _as_float(_first_value(water_rows, "latitude"))
    water_lon = _as_float(_first_value(water_rows, "longitude"))
    weather_lat = _as_float(_first_value(weather_rows, "weather_latitude"))
    weather_lon = _as_float(_first_value(weather_rows, "weather_longitude"))
    weather_distance_km = _haversine_km(water_lat, water_lon, weather_lat, weather_lon)
    if weather_distance_km is not None:
        merged["water_weather_distance_km"] = round(weather_distance_km, 4)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "zhangjiabang_proxy_daily.csv"
    summary_path = output_dir / "zhangjiabang_proxy_summary.json"
    merged.to_csv(csv_path, index=False, encoding="utf-8-sig")

    weather_output_fields = list(WEATHER_FIELD_MAP.values())
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_site": target_site,
        "proxy_status": "substitute_not_direct_measurement",
        "direct_local_data_status": "not_found_in_current_data_or_docs",
        "water_quality_proxy": {
            "station_code": str(water_station_code),
            "station_name": str(_first_value(water_rows, "station_name")),
            "province": str(_first_value(water_rows, "province")),
            "city": str(_first_value(water_rows, "city")),
            "basin": str(_first_value(water_rows, "basin")),
            "river": str(_first_value(water_rows, "river")),
            "longitude": water_lon,
            "latitude": water_lat,
            "rows": int(len(water_rows)),
            "date_range": _date_range(water_rows),
            "source_path": water_quality_path.relative_to(PROJECT_ROOT).as_posix(),
        },
        "weather_proxy": {
            "station_id": str(weather_station_id),
            "station_name": str(_first_value(weather_rows, "weather_station_name")),
            "district": str(_first_value(weather_rows, "weather_district")),
            "city": str(_first_value(weather_rows, "weather_city")),
            "province": str(_first_value(weather_rows, "weather_province")),
            "longitude": weather_lon,
            "latitude": weather_lat,
            "rows": int(len(weather_rows)),
            "date_range": _date_range(weather_rows),
            "source_path": weather_path.relative_to(PROJECT_ROOT).as_posix(),
        },
        "overlap": {
            "rows": int(len(merged)),
            "date_range": _date_range(merged),
            "coverage_against_water_quality_rows": len(merged) / len(water_rows),
            "coverage_against_weather_rows": len(merged) / len(weather_rows),
            "water_weather_distance_km": weather_distance_km,
        },
        "missingness": {
            "water_quality": _missing_summary(merged, list(WATER_FIELDS)),
            "weather": _missing_summary(merged, weather_output_fields),
        },
        "outputs": {
            "daily_csv": csv_path.relative_to(PROJECT_ROOT).as_posix(),
            "summary_json": summary_path.relative_to(PROJECT_ROOT).as_posix(),
        },
        "limitations": [
            "This is a proxy dataset for Zhangjiabang East Gate, not direct Zhangjiabang measurements.",
            "The water-quality series uses Sanjiagang station 2198 on Chuan Yang River.",
            "The weather series uses Pudong station 58370, as requested, instead of the existing nearest-station auto-match.",
            "No UAV, remote-sensing, hydrodynamic, or gate-operation series for Zhangjiabang East Gate were found locally.",
        ],
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    args = parse_args()
    summary = build_proxy_dataset(
        target_site=args.target_site,
        water_station_code=args.water_station_code,
        weather_station_id=args.weather_station_id,
        water_quality_path=args.water_quality_path,
        weather_path=args.weather_path,
        output_dir=args.output_dir,
    )
    outputs = summary["outputs"]
    overlap = summary["overlap"]
    print(f"Saved proxy daily CSV: {outputs['daily_csv']}")
    print(f"Saved proxy summary JSON: {outputs['summary_json']}")
    print(
        "Overlap: "
        f"{overlap['rows']} rows, "
        f"{overlap['date_range']['start']} to {overlap['date_range']['end']}"
    )


if __name__ == "__main__":
    main()
