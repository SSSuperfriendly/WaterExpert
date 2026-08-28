from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from water_ai.data.hydrodynamics import load_or_build_hydrodynamics_daily
from water_ai.data.ndti import load_or_build_ndti_daily_proxy
from water_ai.utils.io import ensure_dir, resolve_single_path, save_json

WATER_RENAME = {
    "\u7701\u4efd": "province",
    "\u57ce\u5e02": "city",
    "\u6d41\u57df": "basin",
    "\u6cb3\u6d41": "river",
    "\u7ad9\u70b9\u540d\u79f0": "station_name",
    "\u7ecf\u5ea6": "longitude",
    "\u7eac\u5ea6": "latitude",
    "\u76d1\u6d4b\u65f6\u95f4": "timestamp",
    "\u6c34\u6e29": "water_temp",
    "pH": "ph",
    "\u6eb6\u89e3\u6c27": "dissolved_oxygen",
    "\u7535\u5bfc\u7387": "conductivity",
    "\u6d4a\u5ea6": "turbidity",
    "\u9ad8\u9530\u9178\u76d0\u6307\u6570": "codmn",
    "\u6c28\u6c2e": "nh3_n",
    "\u603b\u6709\u673a\u78b3": "toc",
    "\u603b\u78f7": "tp",
    "\u603b\u6c2e": "tn",
    "\u53f6\u7eff\u7d20\u03b1": "chlorophyll_a",
    "\u85fb\u5bc6\u5ea6": "algae_density",
    "\u6c34\u8d28": "water_quality_class",
    "\u7ad9\u70b9": "station_status",
}

WEATHER_RENAME = {
    "Station_Id_C": "station_id",
    "Lat": "latitude",
    "Lon": "longitude",
    "Alti": "altitude",
    "City": "city",
    "Station_Name": "weather_station_name",
    "Cnty": "district",
    "Province": "province",
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

HYDRO_FEATURE_COLUMNS = [
    "songpu_flow_m3s",
    "songpu_water_level_m",
    "huangdu_flow_m3s",
    "huangdu_water_level_m",
    "songpu_flow_m3s_abs",
    "songpu_flow_m3s_reverse_flag",
    "songpu_flow_m3s_3d_mean",
    "songpu_flow_m3s_7d_mean",
    "huangdu_flow_m3s_abs",
    "huangdu_flow_m3s_reverse_flag",
    "huangdu_flow_m3s_3d_mean",
    "huangdu_flow_m3s_7d_mean",
    "songpu_water_level_m_1d_diff",
    "songpu_water_level_m_3d_mean",
    "huangdu_water_level_m_1d_diff",
    "huangdu_water_level_m_3d_mean",
    "songpu_flow_level_coupling",
    "huangdu_flow_level_coupling",
    "songpu_flow_m3s_1d_diff",
    "huangdu_flow_m3s_1d_diff",
    "songpu_flow_rise_flag",
    "huangdu_flow_rise_flag",
    "songpu_tidal_pumping_proxy",
    "songpu_resuspension_potential",
    "songpu_flushing_potential",
    "runoff_sediment_pulse",
]

NDTI_FEATURE_COLUMNS = [
    "ndti_annual_proxy",
    "ndti_annual_local_std",
]

BASE_FEATURE_COLUMNS = [
    "water_temp",
    "ph",
    "dissolved_oxygen",
    "conductivity",
    "turbidity",
    "codmn",
    "nh3_n",
    "tp",
    "tn",
    "pressure",
    "air_temp",
    "humidity",
    "precipitation",
    "wind_speed",
    "wind_dir_sin",
    "wind_dir_cos",
    "precipitation_3d",
    "precipitation_7d",
    "pressure_drop",
    "resuspension_index",
    "runoff_proxy",
    "nutrient_risk_index",
    "self_purification_index",
    "mixing_proxy",
    "settling_index",
    "hydrodynamic_intensity",
    "conductivity_anomaly",
    "water_air_temp_gap",
    "dayofyear_sin",
    "dayofyear_cos",
    *NDTI_FEATURE_COLUMNS,
    *HYDRO_FEATURE_COLUMNS,
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * radius_km * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1.0 - a)))


def _load_water_daily(
    data_root: str | Path, water_pattern: str
) -> tuple[pd.DataFrame, dict[str, Any], Path]:
    water_path = resolve_single_path(data_root, water_pattern)
    return _load_water_daily_from_path(water_path)


def _load_water_daily_from_path(
    water_path: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any], Path]:
    water_path = Path(water_path)
    water_df = pd.read_csv(water_path)
    water_df = water_df[water_df["\u76d1\u6d4b\u65f6\u95f4"].notna()].copy()
    water_df = water_df.rename(columns=WATER_RENAME)

    numeric_columns = [
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
    ]
    for column in numeric_columns:
        water_df[column] = pd.to_numeric(water_df[column], errors="coerce")

    water_df["timestamp"] = pd.to_datetime(water_df["timestamp"], errors="coerce")
    water_df = water_df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    water_df["date"] = water_df["timestamp"].dt.floor("D")

    daily_numeric = [
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
    ]
    water_daily = water_df.groupby("date", as_index=False)[daily_numeric].mean()

    station_row = water_df.iloc[0]
    station_meta = {
        "province": station_row.get("province"),
        "city": station_row.get("city"),
        "basin": station_row.get("basin"),
        "river": station_row.get("river"),
        "station_name": station_row.get("station_name"),
        "longitude": float(station_row.get("longitude")),
        "latitude": float(station_row.get("latitude")),
        "raw_rows": int(len(water_df)),
        "daily_rows": int(len(water_daily)),
        "start_date": str(water_daily["date"].min().date()),
        "end_date": str(water_daily["date"].max().date()),
    }
    return water_daily, station_meta, water_path


def _load_weather_daily(weather_path: str | Path) -> pd.DataFrame:
    weather_df = pd.read_csv(weather_path).rename(columns=WEATHER_RENAME)
    weather_df["date"] = pd.to_datetime(
        {"year": weather_df["year"], "month": weather_df["month"], "day": weather_df["day"]},
        errors="coerce",
    )

    numeric_columns = [
        "latitude",
        "longitude",
        "altitude",
        "pressure",
        "air_temp",
        "humidity",
        "precipitation",
        "wind_speed",
        "wind_dir",
    ]
    for column in numeric_columns:
        weather_df[column] = pd.to_numeric(weather_df[column], errors="coerce")

    return weather_df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def _select_weather_station(
    weather_df: pd.DataFrame, water_daily: pd.DataFrame, station_meta: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    water_dates = set(pd.to_datetime(water_daily["date"]))
    station_records: list[dict[str, Any]] = []

    for station_id, station_df in weather_df.groupby("station_id", sort=False):
        station_dates = set(pd.to_datetime(station_df["date"]))
        overlap = len(water_dates & station_dates)
        first = station_df.iloc[0]
        distance_km = _haversine_km(
            float(station_meta["latitude"]),
            float(station_meta["longitude"]),
            float(first["latitude"]),
            float(first["longitude"]),
        )
        station_records.append(
            {
                "station_id": int(station_id),
                "weather_station_name": first["weather_station_name"],
                "district": first["district"],
                "city": first["city"],
                "overlap_days": overlap,
                "distance_km": distance_km,
            }
        )

    ranking_df = pd.DataFrame(station_records).sort_values(
        ["overlap_days", "distance_km"], ascending=[False, True]
    )
    best_station = ranking_df.iloc[0].to_dict()
    best_weather = weather_df[weather_df["station_id"] == best_station["station_id"]].copy()
    best_weather = best_weather[
        [
            "date",
            "station_id",
            "weather_station_name",
            "district",
            "pressure",
            "air_temp",
            "humidity",
            "precipitation",
            "wind_speed",
            "wind_dir",
        ]
    ].reset_index(drop=True)

    return best_weather, {
        **best_station,
        "all_candidates": ranking_df.head(5).to_dict(orient="records"),
    }


def _merge_optional_hydrodynamics(
    base_df: pd.DataFrame,
    data_root: str | Path,
    output_dir: str | Path,
    hydrodynamics_enabled: bool,
    hydrodynamics_source_path: str | Path | None,
    hydrodynamics_wide_path: str | Path | None,
    hydrodynamics_output_dir: str | Path | None,
) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    if not hydrodynamics_enabled:
        return base_df, None

    hydro_output_dir = (
        Path(hydrodynamics_output_dir)
        if hydrodynamics_output_dir is not None
        else Path(output_dir) / "hydrodynamics_preprocessed"
    )
    hydro_df, hydro_meta = load_or_build_hydrodynamics_daily(
        data_root=data_root,
        output_dir=hydro_output_dir,
        wide_path=hydrodynamics_wide_path,
        source_path=hydrodynamics_source_path,
    )
    hydro_df = hydro_df.sort_values("date").reset_index(drop=True)

    base_start = pd.to_datetime(base_df["date"].min())
    base_end = pd.to_datetime(base_df["date"].max())
    hydro_start = pd.to_datetime(hydro_df["date"].min())
    hydro_end = pd.to_datetime(hydro_df["date"].max())
    overlap_start = max(base_start, hydro_start)
    overlap_end = min(base_end, hydro_end)
    natural_overlap_days = 0
    if overlap_start <= overlap_end:
        natural_overlap_days = int((overlap_end - overlap_start).days) + 1

    matched_days = len(set(pd.to_datetime(base_df["date"])) & set(pd.to_datetime(hydro_df["date"])))
    merged_df = pd.merge(base_df, hydro_df, on="date", how="inner")
    merged_df = merged_df.sort_values("date").reset_index(drop=True)

    hydro_meta = {
        **hydro_meta,
        "merge_summary": {
            "rows_before_hydrodynamics_merge": int(len(base_df)),
            "rows_after_hydrodynamics_merge": int(len(merged_df)),
            "natural_overlap_days": int(natural_overlap_days),
            "matched_overlap_days": int(matched_days),
            "coverage_ratio": float(round(matched_days / max(1, natural_overlap_days), 4)),
            "merge_key": "date",
            "merge_type": "inner",
        },
    }
    return merged_df, hydro_meta


def _merge_optional_ndti(
    base_df: pd.DataFrame,
    data_root: str | Path,
    station_meta: dict[str, Any],
    output_dir: str | Path,
    ndti_enabled: bool,
    ndti_dir: str | Path | None,
    ndti_output_dir: str | Path | None,
) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    if not ndti_enabled:
        return base_df, None

    ndti_dir_output = (
        Path(ndti_output_dir) if ndti_output_dir is not None else Path(output_dir) / "ndti_preprocessed"
    )
    ndti_df, ndti_meta = load_or_build_ndti_daily_proxy(
        data_root=data_root,
        output_dir=ndti_dir_output,
        station_meta=station_meta,
        dates=base_df["date"],
        ndti_dir=ndti_dir,
    )
    merged_df = pd.merge(base_df, ndti_df, on="date", how="left")
    available_years = ndti_meta.get("available_years", [])
    matched_days = int(merged_df["ndti_annual_proxy"].notna().sum())
    ndti_meta = {
        **ndti_meta,
        "merge_summary": {
            "rows_before_ndti_merge": int(len(base_df)),
            "rows_after_ndti_merge": int(len(merged_df)),
            "matched_days": matched_days,
            "coverage_ratio": float(round(matched_days / max(1, len(base_df)), 4)),
            "available_years": available_years,
            "merge_key": "date",
            "merge_type": "left",
        },
    }
    return merged_df, ndti_meta


def _merge_optional_boundary_labels(
    base_df: pd.DataFrame,
    data_root: str | Path,
    boundary_config: dict[str, Any] | None,
    output_dir: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    config = boundary_config or {}
    enabled = bool(config.get("enabled", False))
    if not enabled:
        return base_df, {"enabled": False, "status": "disabled"}

    source_path = config.get("source_path")
    if not source_path:
        return base_df, {"enabled": True, "status": "missing_source_path"}

    resolved_path = Path(source_path)
    if not resolved_path.is_absolute():
        direct_candidate = resolved_path
        data_root_candidate = Path(data_root) / source_path
        resolved_path = (
            direct_candidate
            if direct_candidate.exists()
            else data_root_candidate
        )
    if not resolved_path.exists():
        return base_df, {
            "enabled": True,
            "status": "missing_file",
            "source_path": str(resolved_path),
        }

    date_column = str(config.get("date_column", "date"))
    label_column = str(config.get("label_column", "boundary_label"))
    ratio_column = str(config.get("extent_ratio_column", "boundary_extent_ratio"))
    threshold = float(config.get("extent_ratio_threshold", 0.5))

    boundary_df = pd.read_csv(resolved_path).copy()
    if date_column not in boundary_df.columns:
        raise KeyError(
            f"Boundary label file {resolved_path} is missing required date column {date_column!r}."
        )
    boundary_df["date"] = pd.to_datetime(boundary_df[date_column], errors="coerce").dt.floor("D")
    boundary_df = boundary_df.dropna(subset=["date"])

    if label_column not in boundary_df.columns and ratio_column in boundary_df.columns:
        ratio_values = pd.to_numeric(boundary_df[ratio_column], errors="coerce")
        boundary_df[label_column] = np.where(ratio_values >= threshold, 1.0, 0.0)

    if label_column not in boundary_df.columns:
        raise KeyError(
            f"Boundary label file {resolved_path} must provide {label_column!r} or {ratio_column!r}."
        )

    boundary_df[label_column] = pd.to_numeric(boundary_df[label_column], errors="coerce")
    boundary_df["boundary_label_available"] = boundary_df[label_column].notna().astype(float)

    keep_columns = ["date", label_column, "boundary_label_available"]
    for optional_column in [
        ratio_column,
        "label_source",
        "label_confidence",
        "boundary_zone_name",
        "notes",
    ]:
        if optional_column in boundary_df.columns and optional_column not in keep_columns:
            keep_columns.append(optional_column)

    merged_df = base_df.merge(boundary_df[keep_columns], on="date", how="left")
    if label_column != "boundary_label":
        merged_df = merged_df.rename(columns={label_column: "boundary_label"})
    if ratio_column in merged_df.columns and ratio_column != "boundary_extent_ratio":
        merged_df = merged_df.rename(columns={ratio_column: "boundary_extent_ratio"})
    merged_df["boundary_label_available"] = (
        pd.to_numeric(merged_df["boundary_label_available"], errors="coerce")
        .fillna(0.0)
        .clip(lower=0.0, upper=1.0)
    )
    if "boundary_label" in merged_df.columns:
        merged_df["boundary_label"] = pd.to_numeric(
            merged_df["boundary_label"], errors="coerce"
        )
    if "boundary_extent_ratio" in merged_df.columns:
        merged_df["boundary_extent_ratio"] = pd.to_numeric(
            merged_df["boundary_extent_ratio"], errors="coerce"
        )
    if "label_confidence" in merged_df.columns:
        merged_df["label_confidence"] = pd.to_numeric(
            merged_df["label_confidence"], errors="coerce"
        )

    boundary_output_dir = ensure_dir(Path(output_dir) / "boundary")
    available_mask = merged_df["boundary_label_available"].fillna(0.0) > 0.0
    merged_df.loc[
        available_mask,
        [
            "date",
            "boundary_label",
            "boundary_label_available",
            *[
                column
                for column in [
                    "boundary_extent_ratio",
                    "label_source",
                    "label_confidence",
                    "boundary_zone_name",
                ]
                if column in merged_df.columns
            ],
        ],
    ].to_csv(
        boundary_output_dir / "merged_boundary_labels.csv",
        index=False,
        encoding="utf-8-sig",
    )

    return merged_df, {
        "enabled": True,
        "status": "loaded",
        "source_path": str(resolved_path),
        "labeled_days": int(available_mask.sum()),
        "positive_days": int(
            merged_df.loc[available_mask, "boundary_label"].fillna(0.0).sum()
        ),
        "label_column": "boundary_label",
        "extent_ratio_threshold": threshold,
    }


def _engineer_features(merged_df: pd.DataFrame) -> pd.DataFrame:
    df = merged_df.sort_values("date").reset_index(drop=True).copy()
    df["wind_dir"] = df["wind_dir"].fillna(df["wind_dir"].median())
    radians = np.deg2rad(df["wind_dir"].fillna(0.0))
    df["wind_dir_sin"] = np.sin(radians)
    df["wind_dir_cos"] = np.cos(radians)

    df["precipitation"] = df["precipitation"].fillna(0.0)
    df["precipitation_3d"] = df["precipitation"].rolling(3, min_periods=1).sum()
    df["precipitation_7d"] = df["precipitation"].rolling(7, min_periods=1).sum()
    df["pressure_drop"] = (-df["pressure"].diff()).clip(lower=0.0).fillna(0.0)

    conductivity_mean = df["conductivity"].rolling(7, min_periods=1).mean()
    df["conductivity_anomaly"] = df["conductivity"] - conductivity_mean
    df["mixing_proxy"] = df["wind_speed"].fillna(0.0) * (1.0 + np.abs(df["wind_dir_sin"]))
    df["resuspension_index"] = df["wind_speed"].fillna(0.0) * (
        1.0 + df["precipitation_3d"].fillna(0.0)
    )
    df["runoff_proxy"] = df["precipitation_7d"].fillna(0.0) * (
        1.0 + df["humidity"].fillna(0.0) / 100.0
    )
    df["nutrient_risk_index"] = (
        df["nh3_n"].fillna(0.0) + df["tn"].fillna(0.0) + 10.0 * df["tp"].fillna(0.0)
    )
    df["self_purification_index"] = df["dissolved_oxygen"].fillna(0.0) / (
        1.0 + df["codmn"].fillna(0.0) + df["nh3_n"].fillna(0.0) + 10.0 * df["tp"].fillna(0.0)
    )
    df["settling_index"] = 1.0 / (
        1.0
        + df["wind_speed"].fillna(0.0)
        + df["precipitation_3d"].fillna(0.0)
        + df["pressure_drop"].fillna(0.0)
    )

    hydrodynamic_intensity = (
        0.6 * df["wind_speed"].fillna(0.0)
        + 0.2 * df["precipitation_3d"].fillna(0.0)
        + 0.2 * df["pressure_drop"].fillna(0.0)
    )
    if "songpu_flow_m3s_abs" in df.columns:
        songpu_flow_signal = np.log1p(df["songpu_flow_m3s_abs"].clip(lower=0.0))
        hydrodynamic_intensity = hydrodynamic_intensity + 0.25 * songpu_flow_signal
        df["mixing_proxy"] = df["mixing_proxy"] + 0.15 * songpu_flow_signal
    if "songpu_water_level_m_1d_diff" in df.columns:
        songpu_level_jump = df["songpu_water_level_m_1d_diff"].abs().fillna(0.0)
        hydrodynamic_intensity = hydrodynamic_intensity + 0.10 * songpu_level_jump
        df["resuspension_index"] = df["resuspension_index"] + 0.35 * songpu_level_jump
    if "songpu_flow_m3s_reverse_flag" in df.columns:
        reverse_flow = df["songpu_flow_m3s_reverse_flag"].fillna(0.0)
        hydrodynamic_intensity = hydrodynamic_intensity + 0.10 * reverse_flow
        df["resuspension_index"] = df["resuspension_index"] + 0.20 * reverse_flow
    if "songpu_flow_level_coupling" in df.columns:
        coupling_signal = np.log1p(df["songpu_flow_level_coupling"].abs().clip(lower=0.0))
        hydrodynamic_intensity = hydrodynamic_intensity + 0.15 * coupling_signal
    if "huangdu_flow_m3s_3d_mean" in df.columns:
        df["runoff_proxy"] = df["runoff_proxy"] + 0.15 * np.log1p(
            df["huangdu_flow_m3s_3d_mean"].abs().clip(lower=0.0)
        )
    if "songpu_flow_m3s_7d_mean" in df.columns:
        df["self_purification_index"] = df["self_purification_index"] * (
            1.0 + 0.02 * np.log1p(df["songpu_flow_m3s_7d_mean"].clip(lower=0.0))
        )

    if "songpu_flow_m3s" in df.columns:
        df["songpu_flow_m3s_1d_diff"] = df["songpu_flow_m3s"].diff().fillna(0.0)
        df["songpu_flow_rise_flag"] = (df["songpu_flow_m3s_1d_diff"] > 0).astype(float)
    if "huangdu_flow_m3s" in df.columns:
        df["huangdu_flow_m3s_1d_diff"] = df["huangdu_flow_m3s"].diff().fillna(0.0)
        df["huangdu_flow_rise_flag"] = (df["huangdu_flow_m3s_1d_diff"] > 0).astype(float)
    if {
        "songpu_flow_m3s_abs",
        "songpu_flow_m3s_reverse_flag",
        "songpu_water_level_m_1d_diff",
    }.issubset(df.columns):
        df["songpu_tidal_pumping_proxy"] = (
            df["songpu_flow_m3s_abs"].fillna(0.0)
            * df["songpu_flow_m3s_reverse_flag"].fillna(0.0)
            * (1.0 + df["songpu_water_level_m_1d_diff"].abs().fillna(0.0))
        )
    if {
        "songpu_flow_m3s_abs",
        "songpu_flow_m3s_1d_diff",
        "songpu_water_level_m_1d_diff",
    }.issubset(df.columns):
        df["songpu_resuspension_potential"] = (
            (
                df["songpu_flow_m3s_abs"].fillna(0.0)
                + df["songpu_flow_m3s_1d_diff"].abs().fillna(0.0)
            )
            * (1.0 + df["songpu_water_level_m_1d_diff"].abs().fillna(0.0))
        )
    if "songpu_flow_m3s_3d_mean" in df.columns:
        df["songpu_flushing_potential"] = np.clip(
            df["songpu_flow_m3s_3d_mean"].fillna(0.0), a_min=0.0, a_max=None
        ) / (1.0 + df["turbidity"].fillna(0.0))
    if {"precipitation_3d", "huangdu_flow_m3s_1d_diff"}.issubset(df.columns):
        df["runoff_sediment_pulse"] = df["precipitation_3d"].fillna(0.0) * np.clip(
            df["huangdu_flow_m3s_1d_diff"].fillna(0.0), a_min=0.0, a_max=None
        )

    df["hydrodynamic_intensity"] = hydrodynamic_intensity
    df["water_air_temp_gap"] = df["water_temp"].fillna(df["water_temp"].median()) - df[
        "air_temp"
    ].fillna(df["air_temp"].median())

    day_of_year = df["date"].dt.dayofyear.astype(float)
    df["dayofyear_sin"] = np.sin(2.0 * np.pi * day_of_year / 365.25)
    df["dayofyear_cos"] = np.cos(2.0 * np.pi * day_of_year / 365.25)

    turbidity_log = np.log1p(df["turbidity"].clip(lower=0.0))
    log_min = turbidity_log.min()
    log_max = turbidity_log.max()
    scaled = (turbidity_log - log_min) / max(1e-6, float(log_max - log_min))
    df["clearness_proxy"] = 1.0 - scaled

    return df


def build_multimodal_dataset(
    data_root: str | Path,
    water_pattern: str,
    weather_filename: str,
    output_dir: str | Path,
    hydrodynamics_enabled: bool = False,
    hydrodynamics_source_path: str | Path | None = None,
    hydrodynamics_wide_path: str | Path | None = None,
    hydrodynamics_output_dir: str | Path | None = None,
    ndti_enabled: bool = False,
    ndti_dir: str | Path | None = None,
    ndti_output_dir: str | Path | None = None,
    boundary_config: dict[str, Any] | None = None,
    water_path: str | Path | None = None,
    weather_path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    output_dir = ensure_dir(output_dir)
    intermediate_dir = ensure_dir(Path(output_dir) / "intermediate")

    if water_path is not None:
        water_daily, station_meta, water_path = _load_water_daily_from_path(water_path)
    else:
        water_daily, station_meta, water_path = _load_water_daily(data_root, water_pattern)
    weather_df = _load_weather_daily(
        Path(weather_path) if weather_path is not None else Path(data_root) / weather_filename
    )
    selected_weather, weather_meta = _select_weather_station(weather_df, water_daily, station_meta)

    merged_df = pd.merge(water_daily, selected_weather, on="date", how="inner")
    merged_df, hydrodynamics_meta = _merge_optional_hydrodynamics(
        base_df=merged_df,
        data_root=data_root,
        output_dir=output_dir,
        hydrodynamics_enabled=hydrodynamics_enabled,
        hydrodynamics_source_path=hydrodynamics_source_path,
        hydrodynamics_wide_path=hydrodynamics_wide_path,
        hydrodynamics_output_dir=hydrodynamics_output_dir,
    )
    merged_df, ndti_meta = _merge_optional_ndti(
        base_df=merged_df,
        data_root=data_root,
        station_meta=station_meta,
        output_dir=output_dir,
        ndti_enabled=ndti_enabled,
        ndti_dir=ndti_dir,
        ndti_output_dir=ndti_output_dir,
    )
    merged_df, boundary_meta = _merge_optional_boundary_labels(
        base_df=merged_df,
        data_root=data_root,
        boundary_config=boundary_config,
        output_dir=output_dir,
    )
    merged_df = _engineer_features(merged_df)

    boundary_metadata_columns = [
        column
        for column in [
            "boundary_label",
            "boundary_label_available",
            "boundary_extent_ratio",
            "label_confidence",
        ]
        if column in merged_df.columns
    ]
    numeric_columns = merged_df.select_dtypes(include=[np.number]).columns.tolist()
    drop_columns = []
    for column in numeric_columns:
        if column in boundary_metadata_columns:
            continue
        missing_ratio = float(merged_df[column].isna().mean())
        if missing_ratio >= 0.85:
            drop_columns.append(column)
    merged_df = merged_df.drop(columns=drop_columns)

    numeric_columns = merged_df.select_dtypes(include=[np.number]).columns.tolist()
    boundary_metadata_columns = [column for column in boundary_metadata_columns if column in numeric_columns]
    interpolated_columns = [
        column for column in numeric_columns if column not in boundary_metadata_columns
    ]
    if interpolated_columns:
        merged_df[interpolated_columns] = (
            merged_df[interpolated_columns]
            .interpolate(limit_direction="both")
            .ffill()
            .bfill()
        )
    if "boundary_label_available" in merged_df.columns:
        merged_df["boundary_label_available"] = (
            pd.to_numeric(merged_df["boundary_label_available"], errors="coerce")
            .fillna(0.0)
            .clip(lower=0.0, upper=1.0)
        )

    feature_columns = []
    for column in BASE_FEATURE_COLUMNS:
        if column not in merged_df.columns:
            continue
        if merged_df[column].nunique(dropna=True) <= 1:
            continue
        feature_columns.append(column)

    dataset_path = intermediate_dir / "multimodal_daily_dataset.csv"
    merged_df.to_csv(dataset_path, index=False, encoding="utf-8-sig")
    if ndti_enabled:
        merged_df.to_csv(
            intermediate_dir / "multimodal_daily_dataset_with_ndti.csv",
            index=False,
            encoding="utf-8-sig",
        )

    summary = {
        "water_source_path": str(water_path),
        "weather_source_path": str(
            Path(weather_path) if weather_path is not None else Path(data_root) / weather_filename
        ),
        "hydrodynamics_enabled": hydrodynamics_enabled,
        "hydrodynamics": hydrodynamics_meta,
        "ndti_enabled": ndti_enabled,
        "ndti": ndti_meta,
        "boundary_labels": boundary_meta,
        "water_station": station_meta,
        "selected_weather_station": weather_meta,
        "rows_after_merge": int(len(merged_df)),
        "date_range": {
            "start": str(merged_df["date"].min().date()),
            "end": str(merged_df["date"].max().date()),
        },
        "clearness_transform": {
            "log_turbidity_min": float(np.log1p(merged_df["turbidity"].clip(lower=0.0)).min()),
            "log_turbidity_max": float(np.log1p(merged_df["turbidity"].clip(lower=0.0)).max()),
        },
        "feature_columns": feature_columns,
        "dropped_high_missing_columns": drop_columns,
        "targets": (
            ["turbidity", "clearness_proxy", "boundary_label"]
            if boundary_meta.get("status") == "loaded"
            else ["turbidity", "clearness_proxy"]
        ),
        "notes": {
            "current_scope": "single-station multimodal daily prototype",
            "boundary_detection_head": (
                "supervision-ready interface implemented; boundary labels loaded for training"
                if boundary_meta.get("status") == "loaded"
                else "supervision-ready interface implemented, waiting for raster/UAV boundary labels"
            ),
            "spatial_graph": (
                "implemented as a feature factor graph because only one numeric "
                "water-quality station is currently available"
            ),
        },
    }
    save_json(summary, intermediate_dir / "multimodal_dataset_summary.json")
    return merged_df, summary
