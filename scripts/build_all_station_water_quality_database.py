from __future__ import annotations

import csv
import io
import json
import math
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(r"G:\AI4S")
WATER_ARCHIVE_PATH = ROOT / "水质数据.zip"
WEATHER_SOURCE_PATH = ROOT / "daily_version_A_keep_missing.csv"
DELIVERY_DIR = ROOT / "全站水质综合数据库_20260415_完整版"
DELIVERY_ZIP_PATH = ROOT / "全站水质综合数据库_20260415_完整版.zip"

RAW_DIR = DELIVERY_DIR / "00_原始来源"
PROCESSED_DIR = DELIVERY_DIR / "01_预处理数据"
PER_STATION_DIR = PROCESSED_DIR / "per_station_daily_with_secchi"
DOCS_DIR = DELIVERY_DIR / "02_说明文档"
EXCLUDED_RAW_DIR = RAW_DIR / "异常站点原始CSV"

MIN_RAW_ROWS_FOR_MAIN = 30

WATER_RENAME = {
    "省份": "province",
    "城市": "city",
    "流域": "basin",
    "河流": "river",
    "站点名称": "station_name",
    "经度": "longitude",
    "纬度": "latitude",
    "监测时间": "timestamp",
    "水温": "water_temp",
    "pH": "ph",
    "溶解氧": "dissolved_oxygen",
    "电导率": "conductivity",
    "浊度": "turbidity",
    "高锰酸盐指数": "codmn",
    "氨氮": "nh3_n",
    "总有机碳": "toc",
    "总磷": "tp",
    "总氮": "tn",
    "叶绿素α": "chlorophyll_a",
    "藻密度": "algae_density",
    "水质": "water_quality_class",
    "站点": "station_status",
}

RAW_NUMERIC_COLUMNS = [
    "经度",
    "纬度",
    "水温",
    "pH",
    "溶解氧",
    "电导率",
    "浊度",
    "高锰酸盐指数",
    "氨氮",
    "总有机碳",
    "总磷",
    "总氮",
    "叶绿素α",
    "藻密度",
]

RAW_TEXT_COLUMNS = [
    "省份",
    "城市",
    "流域",
    "河流",
    "站点名称",
    "水质",
    "站点",
]

MAIN_OUTPUT_COLUMNS = [
    "date",
    "station_code",
    "station_name",
    "province",
    "city",
    "basin",
    "river",
    "longitude",
    "latitude",
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
    "source_file",
]

WEATHER_RENAME = {
    "Station_Id_C": "weather_station_id",
    "Lat": "weather_latitude",
    "Lon": "weather_longitude",
    "Alti": "weather_altitude",
    "City": "weather_city",
    "Station_Name": "weather_station_name",
    "Cnty": "weather_district",
    "Province": "weather_province",
    "Year": "year",
    "Mon": "month",
    "Day": "day",
    "\u6c14\u538b": "pressure",
    "\u5e73\u5747\u6c14\u6e29": "air_temp",
    "\u76f8\u5bf9\u6e7f\u5ea6": "humidity",
    "\u5f53\u5929\u964d\u6c34\u91cf": "precipitation",
    "\u5e73\u5747\u98ce\u901f": "wind_speed",
    "\u5e73\u5747\u98ce\u5411": "wind_dir",
}

WEATHER_OUTPUT_COLUMNS = [
    "pressure",
    "air_temp",
    "humidity",
    "precipitation",
    "wind_speed",
    "wind_dir",
]


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def estimate_secchi_depth(ntu: float) -> float:
    if pd.isna(ntu) or float(ntu) <= 0.0:
        return math.nan
    return 1.5 / (float(ntu) ** 0.7)


def add_secchi_column(df: pd.DataFrame, turbidity_col: str = "turbidity") -> pd.DataFrame:
    out = df.copy()
    out["secchi_depth_sd_m"] = out[turbidity_col].apply(estimate_secchi_depth)
    out["secchi_formula"] = "SD = 1.5 / NTU^0.7"
    return out


def extract_station_code(file_name: str) -> str:
    match = re.search(r"_(\d+)\.csv$", file_name)
    return match.group(1) if match else ""


def sanitize_filename(name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]+', "_", str(name)).strip()
    return safe or "unknown_station"


def read_csv_from_zip(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> pd.DataFrame:
    raw_bytes = archive.read(member.filename)
    return pd.read_csv(io.BytesIO(raw_bytes))


def preprocess_station_dataframe(raw_df: pd.DataFrame, source_file: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = raw_df.copy()
    df = df[df["监测时间"].notna()].copy()

    for column in RAW_NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df["监测时间"] = pd.to_datetime(df["监测时间"], errors="coerce")
    df = df.dropna(subset=["监测时间"]).sort_values("监测时间").reset_index(drop=True)
    df["date"] = df["监测时间"].dt.floor("D").dt.date.astype(str)

    agg: dict[str, str] = {column: "first" for column in RAW_TEXT_COLUMNS if column in df.columns}
    agg.update({column: "mean" for column in RAW_NUMERIC_COLUMNS if column in df.columns})

    daily = df.groupby("date", as_index=False).agg(agg)
    daily = daily.rename(columns=WATER_RENAME)
    daily["station_code"] = extract_station_code(source_file)
    daily["source_file"] = source_file
    daily = add_secchi_column(daily, "turbidity")

    for column in MAIN_OUTPUT_COLUMNS:
        if column not in daily.columns:
            daily[column] = pd.NA
    daily = daily[MAIN_OUTPUT_COLUMNS].sort_values("date").reset_index(drop=True)

    first_row = daily.iloc[0] if not daily.empty else pd.Series(dtype="object")
    metadata = {
        "station_code": daily["station_code"].iloc[0] if not daily.empty else extract_station_code(source_file),
        "station_name": first_row.get("station_name", ""),
        "province": first_row.get("province", ""),
        "city": first_row.get("city", ""),
        "basin": first_row.get("basin", ""),
        "river": first_row.get("river", ""),
        "longitude": first_row.get("longitude", math.nan),
        "latitude": first_row.get("latitude", math.nan),
        "raw_rows": int(len(df)),
        "daily_rows": int(len(daily)),
        "start_date": daily["date"].min() if not daily.empty else "",
        "end_date": daily["date"].max() if not daily.empty else "",
        "source_file": source_file,
    }
    return daily, metadata


def classify_station(member_name: str, metadata: dict[str, Any]) -> tuple[str, str]:
    station_name = str(metadata.get("station_name", "") or "")
    raw_rows = int(metadata.get("raw_rows", 0))
    if "撤销" in member_name or "撤销" in station_name:
        return "excluded", "withdrawn_station"
    if raw_rows < MIN_RAW_ROWS_FOR_MAIN:
        return "excluded", "too_few_observations"
    return "main", ""


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * radius_km * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1.0 - a)))


def build_station_coverage(main_daily_df: pd.DataFrame) -> pd.DataFrame:
    coverage_columns = [
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
        "secchi_depth_sd_m",
    ]
    rows: list[dict[str, Any]] = []
    for station_code, station_df in main_daily_df.groupby("station_code", sort=True):
        row: dict[str, Any] = {
            "station_code": station_code,
            "station_name": station_df["station_name"].iloc[0],
            "daily_rows": int(len(station_df)),
        }
        for column in coverage_columns:
            row[f"{column}_non_null_ratio"] = round(float(station_df[column].notna().mean()), 4)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["station_code", "station_name"]).reset_index(drop=True)


def load_weather_daily() -> pd.DataFrame:
    weather_df = pd.read_csv(WEATHER_SOURCE_PATH).rename(columns=WEATHER_RENAME)
    weather_df["date"] = pd.to_datetime(
        {"year": weather_df["year"], "month": weather_df["month"], "day": weather_df["day"]},
        errors="coerce",
    )

    numeric_columns = [
        "weather_latitude",
        "weather_longitude",
        "weather_altitude",
        "pressure",
        "air_temp",
        "humidity",
        "precipitation",
        "wind_speed",
        "wind_dir",
    ]
    for column in numeric_columns:
        weather_df[column] = pd.to_numeric(weather_df[column], errors="coerce")

    return weather_df.dropna(subset=["date"]).sort_values(["weather_station_id", "date"]).reset_index(drop=True)


def select_best_weather_station(
    weather_df: pd.DataFrame, station_daily_df: pd.DataFrame, station_meta: pd.Series
) -> tuple[pd.DataFrame, dict[str, Any]]:
    station_dates = set(pd.to_datetime(station_daily_df["date"]))
    station_records: list[dict[str, Any]] = []

    station_lat = float(station_meta["latitude"])
    station_lon = float(station_meta["longitude"])

    for weather_station_id, candidate_df in weather_df.groupby("weather_station_id", sort=False):
        candidate_dates = set(pd.to_datetime(candidate_df["date"]))
        overlap_days = len(station_dates & candidate_dates)
        first = candidate_df.iloc[0]
        distance_km = haversine_km(
            station_lat,
            station_lon,
            float(first["weather_latitude"]),
            float(first["weather_longitude"]),
        )
        station_records.append(
            {
                "weather_station_id": int(weather_station_id),
                "weather_station_name": first["weather_station_name"],
                "weather_district": first["weather_district"],
                "weather_city": first["weather_city"],
                "weather_latitude": float(first["weather_latitude"]),
                "weather_longitude": float(first["weather_longitude"]),
                "overlap_days": int(overlap_days),
                "distance_km": float(distance_km),
            }
        )

    ranking_df = pd.DataFrame(station_records).sort_values(
        ["overlap_days", "distance_km"], ascending=[False, True]
    )
    best = ranking_df.iloc[0].to_dict()
    best_weather_df = weather_df[
        weather_df["weather_station_id"] == best["weather_station_id"]
    ][
        [
            "date",
            "weather_station_id",
            "weather_station_name",
            "weather_district",
            "weather_city",
            "weather_latitude",
            "weather_longitude",
            *WEATHER_OUTPUT_COLUMNS,
        ]
    ].copy()
    return best_weather_df.reset_index(drop=True), {
        **best,
        "candidate_count": int(len(ranking_df)),
    }


def build_station_catalog(station_catalog_all: pd.DataFrame) -> pd.DataFrame:
    station_catalog = station_catalog_all.copy()
    station_catalog["is_available"] = station_catalog["inclusion_status"].eq("main")
    station_catalog["availability_note"] = station_catalog["exclusion_reason"].fillna("main_database")
    station_catalog = station_catalog[
        [
            "station_code",
            "station_name",
            "province",
            "city",
            "basin",
            "river",
            "longitude",
            "latitude",
            "start_date",
            "end_date",
            "raw_rows",
            "daily_rows",
            "is_available",
            "availability_note",
            "source_file",
        ]
    ].sort_values(["is_available", "station_code"], ascending=[False, True])
    return station_catalog.reset_index(drop=True)


def build_multimodal_with_weather(
    all_station_daily_with_secchi: pd.DataFrame, main_station_catalog: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    weather_df = load_weather_daily()
    merged_frames: list[pd.DataFrame] = []
    weather_match_rows: list[dict[str, Any]] = []

    for _, station_row in main_station_catalog.iterrows():
        station_code = station_row["station_code"]
        station_daily_df = all_station_daily_with_secchi[
            all_station_daily_with_secchi["station_code"] == station_code
        ].copy()
        best_weather_df, best_meta = select_best_weather_station(weather_df, station_daily_df, station_row)
        best_weather_df["date"] = pd.to_datetime(best_weather_df["date"]).dt.date.astype(str)
        merged_df = pd.merge(station_daily_df, best_weather_df, on="date", how="left")
        merged_df["weather_distance_km"] = float(best_meta["distance_km"])
        merged_df["weather_overlap_days"] = int(best_meta["overlap_days"])
        merged_frames.append(merged_df)

        matched_weather_days = int(merged_df["pressure"].notna().sum())
        weather_match_rows.append(
            {
                "station_code": station_code,
                "station_name": station_row["station_name"],
                "weather_station_id": int(best_meta["weather_station_id"]),
                "weather_station_name": best_meta["weather_station_name"],
                "weather_district": best_meta["weather_district"],
                "weather_city": best_meta["weather_city"],
                "weather_latitude": float(best_meta["weather_latitude"]),
                "weather_longitude": float(best_meta["weather_longitude"]),
                "weather_distance_km": round(float(best_meta["distance_km"]), 4),
                "water_quality_days": int(len(station_daily_df)),
                "weather_overlap_days": int(best_meta["overlap_days"]),
                "matched_weather_days": matched_weather_days,
            }
        )

    multimodal_df = pd.concat(merged_frames, ignore_index=True).sort_values(["station_code", "date"])
    weather_match_df = pd.DataFrame(weather_match_rows).sort_values(["station_code"]).reset_index(drop=True)
    return multimodal_df.reset_index(drop=True), weather_match_df


def build_modality_summary(
    station_catalog: pd.DataFrame,
    all_station_daily_with_secchi: pd.DataFrame,
    multimodal_weather_df: pd.DataFrame,
    weather_match_df: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for _, station_row in station_catalog.iterrows():
        station_code = station_row["station_code"]
        is_available = bool(station_row["is_available"])
        station_daily_df = all_station_daily_with_secchi[
            all_station_daily_with_secchi["station_code"] == station_code
        ].copy()
        station_multi_df = multimodal_weather_df[
            multimodal_weather_df["station_code"] == station_code
        ].copy()
        weather_match = weather_match_df[weather_match_df["station_code"] == station_code]

        water_quality_days = int(len(station_daily_df)) if is_available else 0
        secchi_days = (
            int(station_daily_df["secchi_depth_sd_m"].notna().sum()) if is_available else 0
        )
        weather_days = int(station_multi_df["pressure"].notna().sum()) if is_available else 0

        has_water_quality = is_available and water_quality_days > 0
        has_secchi = is_available and secchi_days > 0
        has_weather = is_available and weather_days > 0

        available_modalities = [
            name
            for name, enabled in [
                ("water_quality", has_water_quality),
                ("secchi", has_secchi),
                ("weather", has_weather),
            ]
            if enabled
        ]
        missing_modalities = [
            name
            for name, enabled in [
                ("water_quality", has_water_quality),
                ("secchi", has_secchi),
                ("weather", has_weather),
            ]
            if not enabled
        ]

        row: dict[str, Any] = {
            "station_code": station_code,
            "station_name": station_row["station_name"],
            "is_available": is_available,
            "availability_note": station_row["availability_note"],
            "water_quality_days": water_quality_days,
            "secchi_days": secchi_days,
            "weather_days": weather_days,
            "secchi_coverage_ratio": round(secchi_days / max(1, water_quality_days), 4)
            if water_quality_days
            else 0.0,
            "weather_coverage_ratio": round(weather_days / max(1, water_quality_days), 4)
            if water_quality_days
            else 0.0,
            "available_modalities": "|".join(available_modalities),
            "missing_modalities": "|".join(missing_modalities),
        }
        if not weather_match.empty:
            match_row = weather_match.iloc[0]
            row.update(
                {
                    "weather_station_id": int(match_row["weather_station_id"]),
                    "weather_station_name": match_row["weather_station_name"],
                    "weather_district": match_row["weather_district"],
                    "weather_distance_km": float(match_row["weather_distance_km"]),
                    "weather_overlap_days": int(match_row["weather_overlap_days"]),
                }
            )
        else:
            row.update(
                {
                    "weather_station_id": pd.NA,
                    "weather_station_name": pd.NA,
                    "weather_district": pd.NA,
                    "weather_distance_km": pd.NA,
                    "weather_overlap_days": 0,
                }
            )
        rows.append(row)

    return pd.DataFrame(rows).sort_values(["is_available", "station_code"], ascending=[False, True]).reset_index(
        drop=True
    )


def build_all_station_database() -> dict[str, Any]:
    if not WATER_ARCHIVE_PATH.exists():
        raise FileNotFoundError(f"Missing archive: {WATER_ARCHIVE_PATH}")

    ensure_clean_dir(DELIVERY_DIR)
    for folder in [RAW_DIR, PROCESSED_DIR, PER_STATION_DIR, DOCS_DIR, EXCLUDED_RAW_DIR]:
        folder.mkdir(parents=True, exist_ok=True)

    shutil.copy2(WATER_ARCHIVE_PATH, RAW_DIR / WATER_ARCHIVE_PATH.name)

    main_frames: list[pd.DataFrame] = []
    catalog_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, str]] = [
        {"relative_path": str((RAW_DIR / WATER_ARCHIVE_PATH.name).relative_to(DELIVERY_DIR)), "type": "raw_archive"}
    ]

    with zipfile.ZipFile(WATER_ARCHIVE_PATH) as archive:
        csv_members = [member for member in archive.infolist() if member.filename.lower().endswith(".csv")]
        for member in sorted(csv_members, key=lambda item: item.filename):
            raw_df = read_csv_from_zip(archive, member)
            daily_df, metadata = preprocess_station_dataframe(raw_df, source_file=member.filename)
            inclusion_status, exclusion_reason = classify_station(member.filename, metadata)

            catalog_row = {
                **metadata,
                "inclusion_status": inclusion_status,
                "exclusion_reason": exclusion_reason,
                "zip_member_size_bytes": int(member.file_size),
            }
            catalog_rows.append(catalog_row)

            if inclusion_status == "main":
                main_frames.append(daily_df)
                station_file_name = (
                    f"{metadata['station_code']}_{sanitize_filename(metadata['station_name'])}.csv"
                )
                station_path = PER_STATION_DIR / station_file_name
                daily_df.to_csv(station_path, index=False, encoding="utf-8-sig")
                manifest_rows.append(
                    {
                        "relative_path": str(station_path.relative_to(DELIVERY_DIR)),
                        "type": "per_station_daily_with_secchi",
                    }
                )
            else:
                excluded_rows.append(catalog_row)
                excluded_path = EXCLUDED_RAW_DIR / Path(member.filename).name
                excluded_path.write_bytes(archive.read(member.filename))
                manifest_rows.append(
                    {
                        "relative_path": str(excluded_path.relative_to(DELIVERY_DIR)),
                        "type": "excluded_raw_station_csv",
                    }
                )

    station_catalog_all = pd.DataFrame(catalog_rows).sort_values(
        ["inclusion_status", "station_code", "station_name"]
    )
    excluded_station_df = pd.DataFrame(excluded_rows).sort_values(["station_code", "station_name"])
    main_station_catalog = station_catalog_all[
        station_catalog_all["inclusion_status"] == "main"
    ].reset_index(drop=True)

    if not main_frames:
        raise RuntimeError("No main station file was included in the database build.")

    all_station_daily_with_secchi = pd.concat(main_frames, ignore_index=True).sort_values(
        ["station_code", "date"]
    )
    all_station_daily = all_station_daily_with_secchi.drop(
        columns=["secchi_depth_sd_m", "secchi_formula"]
    ).copy()
    station_coverage = build_station_coverage(all_station_daily_with_secchi)
    station_catalog = build_station_catalog(station_catalog_all)
    multimodal_weather_df, weather_match_df = build_multimodal_with_weather(
        all_station_daily_with_secchi=all_station_daily_with_secchi,
        main_station_catalog=main_station_catalog,
    )
    modality_summary_df = build_modality_summary(
        station_catalog=station_catalog,
        all_station_daily_with_secchi=all_station_daily_with_secchi,
        multimodal_weather_df=multimodal_weather_df,
        weather_match_df=weather_match_df,
    )

    all_daily_path = PROCESSED_DIR / "water_quality_daily_all_stations.csv"
    all_daily_secchi_path = PROCESSED_DIR / "water_quality_daily_all_stations_with_secchi.csv"
    multimodal_weather_path = PROCESSED_DIR / "multimodal_daily_all_stations_with_weather.csv"
    modality_summary_path = PROCESSED_DIR / "multimodal_daily_all_stations_modality_summary.csv"
    station_catalog_exact_path = PROCESSED_DIR / "station_catalog.csv"
    station_catalog_path = PROCESSED_DIR / "station_catalog_main.csv"
    station_catalog_all_path = PROCESSED_DIR / "station_catalog_all.csv"
    excluded_path = PROCESSED_DIR / "excluded_station_files.csv"
    coverage_path = PROCESSED_DIR / "station_field_coverage.csv"
    weather_match_path = PROCESSED_DIR / "station_weather_match_summary.csv"

    all_station_daily.to_csv(all_daily_path, index=False, encoding="utf-8-sig")
    all_station_daily_with_secchi.to_csv(all_daily_secchi_path, index=False, encoding="utf-8-sig")
    multimodal_weather_df.to_csv(multimodal_weather_path, index=False, encoding="utf-8-sig")
    modality_summary_df.to_csv(modality_summary_path, index=False, encoding="utf-8-sig")
    station_catalog.to_csv(station_catalog_exact_path, index=False, encoding="utf-8-sig")
    main_station_catalog.to_csv(station_catalog_path, index=False, encoding="utf-8-sig")
    station_catalog_all.to_csv(station_catalog_all_path, index=False, encoding="utf-8-sig")
    excluded_station_df.to_csv(excluded_path, index=False, encoding="utf-8-sig")
    station_coverage.to_csv(coverage_path, index=False, encoding="utf-8-sig")
    weather_match_df.to_csv(weather_match_path, index=False, encoding="utf-8-sig")

    for path, file_type in [
        (all_daily_path, "derived_all_station_daily"),
        (all_daily_secchi_path, "derived_all_station_daily_with_secchi"),
        (multimodal_weather_path, "derived_all_station_water_quality_weather_integrated_daily"),
        (modality_summary_path, "station_dimension_summary"),
        (station_catalog_exact_path, "station_catalog"),
        (station_catalog_path, "station_catalog_main"),
        (station_catalog_all_path, "station_catalog_all"),
        (excluded_path, "excluded_station_list"),
        (coverage_path, "station_field_coverage"),
        (weather_match_path, "station_weather_match_summary"),
    ]:
        manifest_rows.append({"relative_path": str(path.relative_to(DELIVERY_DIR)), "type": file_type})

    summary = {
        "delivery_dir": str(DELIVERY_DIR),
        "zip_path": str(DELIVERY_ZIP_PATH),
        "raw_archive_path": str(WATER_ARCHIVE_PATH),
        "raw_csv_entries_total": int(len(station_catalog_all)),
        "main_station_count": int(len(main_station_catalog)),
        "excluded_station_count": int(len(excluded_station_df)),
        "main_daily_rows_total": int(len(all_station_daily_with_secchi)),
        "integrated_water_quality_weather_rows_total": int(len(multimodal_weather_df)),
        "secchi_formula": "SD = 1.5 / NTU^0.7",
        "weather_source_path": str(WEATHER_SOURCE_PATH),
        "main_station_codes": main_station_catalog["station_code"].astype(str).tolist(),
        "excluded_station_codes": excluded_station_df["station_code"].astype(str).tolist(),
        "main_date_range": {
            "start": str(all_station_daily_with_secchi["date"].min()),
            "end": str(all_station_daily_with_secchi["date"].max()),
        },
    }

    summary_path = DOCS_DIR / "交付摘要.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_rows.append({"relative_path": str(summary_path.relative_to(DELIVERY_DIR)), "type": "summary"})

    readme_content = f"""# 全站水质综合数据库说明

## 1. 本版定位
本次交付的目标不是训练模型，而是先把“库”建完整。

这版 `全站水质综合数据库_20260415_完整版` 与之前的 `多模态水质综合数据库_20260412` 分工不同：
- `20260412` 版偏单站原型，核心围绕吴淞口，包含透明度换算、单站水质-天气-水动力融合以及工程案例整理
- `20260415_完整版` 偏全站基础库，核心是把压缩包中的水质站点统一预处理，并补齐全站天气融合

因此，这一版的定位是：
- 全站统一水质数据库
- 全站基础多维度数据库（`water_quality + secchi + weather`）
- 后续全站水动力、全站 NDTI、全站遥感反演、最终训练集的底座

## 2. 数据来源与总体统计
当前数据库来源于：
- `{WATER_ARCHIVE_PATH.name}`：上海重点流域断面水质原始 CSV
- `{WEATHER_SOURCE_PATH.name}`：上海多站点日尺度气象数据

本次交付的核心统计如下：
- 原始站点数：23
- 主库站点数：20
- 排除站点数：3
- 主库日尺度记录数：31099
- 主库时间范围：2014-04-03 到 2025-10-31

## 3. 主库纳入规则
- `监测时间` 可正常解析
- 原始记录数不少于 {MIN_RAW_ROWS_FOR_MAIN} 条
- 不属于撤销站点

## 4. 你最关心的核心文件
- `01_预处理数据/station_catalog.csv`
  每个站点一行，记录站名、流域、河流、经纬度、时间范围、数据量、是否可用
- `01_预处理数据/water_quality_daily_all_stations.csv`
  所有主库站点统一成日尺度水质表
- `01_预处理数据/water_quality_daily_all_stations_with_secchi.csv`
  在上表基础上增加 `secchi_depth_sd_m`
- `01_预处理数据/multimodal_daily_all_stations_with_weather.csv`
  每个主库站匹配气象站后的全站水质-透明度-天气多维度融合表
- `01_预处理数据/multimodal_daily_all_stations_modality_summary.csv`
  说明每个站当前有哪些维度、哪些缺失
- `02_说明文档/README_数据库说明.md`
  本说明文件，说明字段、公式、来源、可用范围

## 5. 其余辅助文件
- `01_预处理数据/station_catalog_main.csv`
  仅主库 20 个有效站点
- `01_预处理数据/station_catalog_all.csv`
  全部 23 个站点的总目录，含纳入/排除状态
- `01_预处理数据/excluded_station_files.csv`
  3 个未纳入主库的小文件说明
- `01_预处理数据/station_weather_match_summary.csv`
  每个主库站与气象站的匹配关系
- `01_预处理数据/per_station_daily_with_secchi/`
  每个主库站点的单独日尺度结果

## 6. `station_catalog.csv` 字段说明
- `station_code`：站点编码，取自原始文件名尾部编号
- `station_name`：站点名称
- `province`, `city`, `basin`, `river`：省份、城市、流域、河流
- `longitude`, `latitude`：站点经纬度
- `start_date`, `end_date`：该站在主表中的时间范围
- `raw_rows`：原始小时/次级观测记录条数
- `daily_rows`：聚合成日尺度后的记录条数
- `is_available`：是否纳入当前主库
  `True` 表示纳入主库
  `False` 表示单独列为异常/撤销/补充站点
- `availability_note`：是否可用的具体原因
  当前可能值包括：
  `main_database`：已纳入主库
  `withdrawn_station`：撤销站点，不纳入主库
  `too_few_observations`：观测太少，暂不纳入主库
- `source_file`：原始文件在压缩包中的路径

## 7. 排除站点清单
当前排除的 3 个站点如下：
- `3787` 明星路桥（撤销）
  文件名已明确标注“撤销”，不纳入主库
  压缩包中另有 `2587` 明星路桥有效站点，已纳入主库
- `3788` 青草沙进水口
  原始记录仅 1 条，暂不纳入主库
- `6377` 闵行西界
  原始记录仅 7 条，聚合后仅 2 个日尺度记录，暂不纳入主库

对应清单见：
- `01_预处理数据/excluded_station_files.csv`

## 8. 天气匹配规则与说明
`multimodal_daily_all_stations_with_weather.csv` 的构建规则是：
- 先对每个主库站点，统计其与每个气象站的日期重叠天数
- 按“重叠天数从高到低”排序
- 若多个候选站点重叠情况相当，则按空间距离从近到远排序
- 选取排序最优的 1 个气象站作为该水质站的匹配站

对应结果说明文件：
- `01_预处理数据/station_weather_match_summary.csv`

其中主要字段含义为：
- `weather_station_id`, `weather_station_name`：匹配到的气象站编号与名称
- `weather_distance_km`：水质站与气象站的球面距离，单位 km
- `weather_overlap_days`：两者日期重叠天数
- `matched_weather_days`：真正并入多模态表后的有效天气记录天数

说明：
- 虽然文件名中保留了 `multimodal` 历史命名，但这张表在当前版本中的准确含义是“全站水质-透明度-天气多维度融合表”，并非严格意义上的多模态数据集。

## 9. 维度摘要字段说明
`multimodal_daily_all_stations_modality_summary.csv` 主要用于快速看每个站目前可用的维度情况。

其中：
- `available_modalities`：当前站点已具备的维度，以 `|` 分隔
- `missing_modalities`：当前站点缺失的维度，以 `|` 分隔
- `water_quality_days`：该站可用的水质日尺度天数
- `secchi_days`：该站可用的透明度换算天数
- `weather_days`：该站成功并入天气后的天数
- `secchi_coverage_ratio`：`secchi_days / water_quality_days`
- `weather_coverage_ratio`：`weather_days / water_quality_days`

## 10. 字段与单位说明
### 10.1 水质字段
主表字段包括：
- 基础信息：`station_code`, `station_name`, `province`, `city`, `basin`, `river`, `longitude`, `latitude`, `date`
- 水质指标：`water_temp`, `ph`, `dissolved_oxygen`, `conductivity`, `turbidity`, `codmn`, `nh3_n`, `toc`, `tp`, `tn`, `chlorophyll_a`, `algae_density`
- 水质状态：`water_quality_class`, `station_status`

主要单位：
- `water_temp`：摄氏度（℃）
- `ph`：无量纲
- `dissolved_oxygen`：mg/L
- `conductivity`：μS/cm
- `turbidity`：NTU
- `codmn`：mg/L
- `nh3_n`：mg/L
- `toc`：mg/L
- `tp`：mg/L
- `tn`：mg/L
- `chlorophyll_a`：mg/L
- `algae_density`：cells/L

### 10.2 透明度换算
- 字段名：`secchi_depth_sd_m`
- 公式：`SD = 1.5 / NTU^0.7`
- 单位：m
- 说明：这是基于浊度换算得到的透明度 proxy，不是现场实测 Secchi 深度

### 10.3 气象字段
水质-天气融合表新增：
- 气象站信息：`weather_station_id`, `weather_station_name`, `weather_district`, `weather_city`, `weather_distance_km`
- 气象变量：`pressure`, `air_temp`, `humidity`, `precipitation`, `wind_speed`, `wind_dir`

主要单位：
- `pressure`：hPa
- `air_temp`：℃ 
- `humidity`：%
- `precipitation`：mm
- `wind_speed`：m/s
- `wind_dir`：度（0-360）

## 11. 数据来源
- 水质数据：`{WATER_ARCHIVE_PATH}`
- 气象数据：`{WEATHER_SOURCE_PATH}`

## 12. 当前边界与不包含内容
当前这套库解决的是“全站统一水质预处理 + 全站天气融合”。

这版数据库当前明确包含：
- 全站水质日尺度表
- 全站透明度换算结果
- 全站天气匹配后的基础多维度融合表

这版数据库当前明确不包含：
- 全站水动力数据
- 全站 NDTI 数据
- 全站遥感反演产品
- 工程案例结构化表
- 最终模型训练集划分结果

因此，这一版是完整数据库底座，不是最终训练集。
"""
    readme_path = DOCS_DIR / "README_数据库说明.md"
    write_text_file(readme_path, readme_content)
    manifest_rows.append({"relative_path": str(readme_path.relative_to(DELIVERY_DIR)), "type": "readme"})

    manifest_path = DOCS_DIR / "数据清单.csv"
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["relative_path", "type"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    if DELIVERY_ZIP_PATH.exists():
        DELIVERY_ZIP_PATH.unlink()
    shutil.make_archive(str(DELIVERY_ZIP_PATH.with_suffix("")), "zip", DELIVERY_DIR)

    return summary


def main() -> None:
    summary = build_all_station_database()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
