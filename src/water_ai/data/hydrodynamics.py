from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from water_ai.utils.io import ensure_dir, save_json

HUANGDU_NAME = "\u9ec4\u6e21"
SONGPU_NAME = "\u677e\u6d66\u5927\u6865"
SUZHOU_RIVER_NAME = "\u82cf\u5dde\u6cb3/\u5434\u6dde\u6c5f"
HUANGPU_RIVER_NAME = "\u9ec4\u6d66\u6c5f"
DEFAULT_XLS_FILENAME = (
    "\u4e0a\u6d77\u6c34\u57df\u73af\u5883\u53d1\u5c55\u6709\u9650\u516c\u53f8"
    "\u8d44\u6599\u63d0\u4f9b.xls"
)
DEFAULT_LONG_FILENAME = "shanghai_hydrodynamics_daily_long.csv"
DEFAULT_WIDE_FILENAME = "shanghai_hydrodynamics_daily_wide.csv"
DEFAULT_SUMMARY_FILENAME = "summary.json"

FLOW_SHEET_SPECS = [
    {
        "sheet_index": 0,
        "station_name": HUANGDU_NAME,
        "river_name": SUZHOU_RIVER_NAME,
        "station_code": "63405100",
    },
    {
        "sheet_index": 2,
        "station_name": SONGPU_NAME,
        "river_name": HUANGPU_RIVER_NAME,
        "station_code": "63401120",
    },
]

LEVEL_SHEET_SPECS = [
    {
        "sheet_index": 1,
        "station_name": HUANGDU_NAME,
        "river_name": SUZHOU_RIVER_NAME,
        "station_code": "63405100",
    },
    {
        "sheet_index": 3,
        "station_name": SONGPU_NAME,
        "river_name": HUANGPU_RIVER_NAME,
        "station_code": "63401120",
    },
]


def resolve_hydrodynamics_xls(
    data_root: str | Path,
    source_path: str | Path | None = None,
) -> Path:
    data_root = Path(data_root)
    candidates = []

    if source_path:
        source_path = Path(source_path)
        candidates.append(source_path)
        if not source_path.is_absolute():
            candidates.append(data_root / source_path)

    candidates.append(data_root / DEFAULT_XLS_FILENAME)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    matches = sorted(data_root.glob("*.xls"))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(
            f"Could not locate a hydrodynamics .xls file under {data_root}. "
            "Provide hydrodynamics_source_path explicitly."
        )
    raise RuntimeError(
        f"Found multiple .xls files under {data_root}: {matches}. "
        "Provide hydrodynamics_source_path explicitly."
    )


def parse_flow_sheet(xls_path: str | Path, spec: dict[str, str]) -> pd.DataFrame:
    raw = pd.read_excel(xls_path, sheet_name=spec["sheet_index"], header=None)
    year_blocks = [
        {"year": int(raw.iloc[1, 2]), "day_col": 0, "month_start": 2},
        {"year": int(raw.iloc[1, 17]), "day_col": 15, "month_start": 17},
        {"year": int(raw.iloc[1, 32]), "day_col": 30, "month_start": 32},
    ]

    rows: list[dict[str, Any]] = []
    for block in year_blocks:
        for row_index in range(4, raw.shape[0]):
            day = pd.to_numeric(raw.iloc[row_index, block["day_col"]], errors="coerce")
            if pd.isna(day):
                continue
            day = int(day)

            for offset in range(12):
                value = pd.to_numeric(
                    raw.iloc[row_index, block["month_start"] + offset], errors="coerce"
                )
                if pd.isna(value):
                    continue
                try:
                    date = pd.Timestamp(year=block["year"], month=offset + 1, day=day)
                except ValueError:
                    continue
                rows.append(
                    {
                        "date": date,
                        "station_name": spec["station_name"],
                        "river_name": spec["river_name"],
                        "station_code": spec["station_code"],
                        "variable": "flow",
                        "value": float(value),
                        "unit": "m3/s",
                        "source_sheet_index": spec["sheet_index"],
                    }
                )

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def parse_level_sheet(xls_path: str | Path, spec: dict[str, str]) -> pd.DataFrame:
    df = pd.read_excel(xls_path, sheet_name=spec["sheet_index"]).copy()
    df.columns = ["date", "value"]
    df["station_name"] = spec["station_name"]
    df["river_name"] = spec["river_name"]
    df["station_code"] = spec["station_code"]
    df["variable"] = "water_level"
    df["unit"] = "m"
    df["source_sheet_index"] = spec["sheet_index"]
    return df.sort_values("date").reset_index(drop=True)


def build_wide_table(long_df: pd.DataFrame) -> pd.DataFrame:
    wide_df = (
        long_df.assign(column_name=lambda df: df["station_name"] + "_" + df["variable"])
        .pivot_table(index="date", columns="column_name", values="value", aggfunc="first")
        .reset_index()
        .sort_values("date")
        .reset_index(drop=True)
    )

    rename_map = {
        f"{HUANGDU_NAME}_flow": "huangdu_flow_m3s",
        f"{HUANGDU_NAME}_water_level": "huangdu_water_level_m",
        f"{SONGPU_NAME}_flow": "songpu_flow_m3s",
        f"{SONGPU_NAME}_water_level": "songpu_water_level_m",
    }
    wide_df = wide_df.rename(columns=rename_map)

    for flow_col in ["huangdu_flow_m3s", "songpu_flow_m3s"]:
        if flow_col not in wide_df.columns:
            continue
        wide_df[f"{flow_col}_abs"] = wide_df[flow_col].abs()
        wide_df[f"{flow_col}_reverse_flag"] = (wide_df[flow_col] < 0).astype(int)
        wide_df[f"{flow_col}_3d_mean"] = wide_df[flow_col].rolling(3, min_periods=1).mean()
        wide_df[f"{flow_col}_7d_mean"] = wide_df[flow_col].rolling(7, min_periods=1).mean()

    for level_col in ["huangdu_water_level_m", "songpu_water_level_m"]:
        if level_col not in wide_df.columns:
            continue
        wide_df[f"{level_col}_1d_diff"] = wide_df[level_col].diff().fillna(0.0)
        wide_df[f"{level_col}_3d_mean"] = wide_df[level_col].rolling(3, min_periods=1).mean()

    if {"songpu_flow_m3s", "songpu_water_level_m"}.issubset(wide_df.columns):
        wide_df["songpu_flow_level_coupling"] = (
            wide_df["songpu_flow_m3s"] * wide_df["songpu_water_level_m"]
        )
    if {"huangdu_flow_m3s", "huangdu_water_level_m"}.issubset(wide_df.columns):
        wide_df["huangdu_flow_level_coupling"] = (
            wide_df["huangdu_flow_m3s"] * wide_df["huangdu_water_level_m"]
        )

    return wide_df


def build_hydrodynamics_summary(
    xls_path: str | Path,
    long_df: pd.DataFrame,
    wide_df: pd.DataFrame,
    long_path: str | Path | None = None,
    wide_path: str | Path | None = None,
) -> dict[str, Any]:
    stations = sorted(long_df["station_name"].dropna().unique().tolist())
    return {
        "source_xls": str(xls_path),
        "preprocessed_long_path": str(long_path) if long_path else None,
        "preprocessed_wide_path": str(wide_path) if wide_path else None,
        "long_rows": int(len(long_df)),
        "wide_rows": int(len(wide_df)),
        "date_range": {
            "start": str(wide_df["date"].min().date()),
            "end": str(wide_df["date"].max().date()),
        },
        "stations": stations,
        "variables": sorted(long_df["variable"].dropna().unique().tolist()),
        "negative_flow_counts": {
            station: int(
                (
                    (long_df["station_name"] == station)
                    & (long_df["variable"] == "flow")
                    & (long_df["value"] < 0)
                ).sum()
            )
            for station in stations
        },
        "recommended_primary_station_for_current_model": SONGPU_NAME,
        "recommended_reason": (
            "\u5f53\u524d\u5df2\u6709\u6c34\u8d28\u7ad9\u70b9\u4e3a"
            "\u9ec4\u6d66\u6c5f\u5434\u6dde\u53e3\uff0c\u677e\u6d66\u5927\u6865"
            "\u6c34\u52a8\u529b\u4e0e\u5176\u6cb3\u9053\u5173\u8054\u6027\u66f4\u5f3a\u3002"
        ),
    }


def preprocess_hydrodynamics_xls(
    xls_path: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    xls_path = Path(xls_path)
    flow_frames = [parse_flow_sheet(xls_path, spec) for spec in FLOW_SHEET_SPECS]
    level_frames = [parse_level_sheet(xls_path, spec) for spec in LEVEL_SHEET_SPECS]

    long_df = pd.concat(flow_frames + level_frames, ignore_index=True).sort_values(
        ["station_name", "variable", "date"]
    )
    wide_df = build_wide_table(long_df)

    long_path = None
    wide_path = None
    if output_dir is not None:
        output_dir = ensure_dir(output_dir)
        long_path = output_dir / DEFAULT_LONG_FILENAME
        wide_path = output_dir / DEFAULT_WIDE_FILENAME
        long_df.to_csv(long_path, index=False, encoding="utf-8-sig")
        wide_df.to_csv(wide_path, index=False, encoding="utf-8-sig")

    summary = build_hydrodynamics_summary(
        xls_path=xls_path,
        long_df=long_df,
        wide_df=wide_df,
        long_path=long_path,
        wide_path=wide_path,
    )
    if output_dir is not None:
        save_json(summary, Path(output_dir) / DEFAULT_SUMMARY_FILENAME)

    return long_df, wide_df, summary


def load_or_build_hydrodynamics_daily(
    data_root: str | Path,
    output_dir: str | Path,
    wide_path: str | Path | None = None,
    source_path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    output_dir = ensure_dir(output_dir)
    summary_path = output_dir / DEFAULT_SUMMARY_FILENAME

    candidate_wide_paths: list[Path] = []
    if wide_path:
        wide_path = Path(wide_path)
        candidate_wide_paths.append(wide_path)
        if not wide_path.is_absolute():
            candidate_wide_paths.append(Path(data_root) / wide_path)
    candidate_wide_paths.append(output_dir / DEFAULT_WIDE_FILENAME)

    for candidate in candidate_wide_paths:
        if not candidate.exists():
            continue
        hydro_df = pd.read_csv(candidate, parse_dates=["date"]).sort_values("date").reset_index(
            drop=True
        )
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        else:
            summary = {
                "preprocessed_wide_path": str(candidate),
                "wide_rows": int(len(hydro_df)),
                "date_range": {
                    "start": str(hydro_df["date"].min().date()),
                    "end": str(hydro_df["date"].max().date()),
                },
            }
        summary["preprocessed_wide_path"] = str(candidate)
        return hydro_df, summary

    xls_path = resolve_hydrodynamics_xls(data_root=data_root, source_path=source_path)
    _, hydro_df, summary = preprocess_hydrodynamics_xls(xls_path=xls_path, output_dir=output_dir)
    return hydro_df, summary
