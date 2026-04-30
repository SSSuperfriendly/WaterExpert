from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image

from water_ai.utils.io import ensure_dir, save_json

DEFAULT_NDTI_FILENAME = "ndti_annual_station_proxy.csv"
DEFAULT_NDTI_SUMMARY = "ndti_summary.json"
NDTI_NODATA_VALUE = -1.3333333730697632
YEAR_PATTERN = re.compile(r"turbidity_(\d{4})\.tif$", re.IGNORECASE)


def resolve_ndti_dir(data_root: str | Path, ndti_dir: str | Path | None = None) -> Path:
    if ndti_dir is not None:
        path = Path(ndti_dir)
        if path.exists():
            return path
        raise FileNotFoundError(f"NDTI directory does not exist: {path}")

    candidate = Path(data_root) / "turbidity"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        f"Could not locate a turbidity/NDTI directory under {data_root}. "
        "Provide ndti_dir explicitly."
    )


def _load_tiff_array(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    image = Image.open(path)
    tags = image.tag_v2
    array = np.array(image, dtype=np.float32)
    pixel_scale = tags.get(33550)
    tie_point = tags.get(33922)
    crs_name = tags.get(34737, "unknown")
    description = tags.get(42112, "")
    if pixel_scale is None or tie_point is None:
        raise ValueError(f"GeoTIFF tags missing in {path}")

    pixel_size_x = float(pixel_scale[0])
    pixel_size_y = float(pixel_scale[1])
    origin_x = float(tie_point[3])
    origin_y = float(tie_point[4])
    width, height = image.size
    bounds = {
        "xmin": origin_x,
        "xmax": origin_x + width * pixel_size_x,
        "ymax": origin_y,
        "ymin": origin_y - height * pixel_size_y,
    }
    meta = {
        "width": int(width),
        "height": int(height),
        "pixel_size_x": pixel_size_x,
        "pixel_size_y": pixel_size_y,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "bounds": bounds,
        "crs": str(crs_name),
        "description": str(description),
    }
    return array, meta


def _extract_year(path: Path) -> int:
    match = YEAR_PATTERN.search(path.name)
    if not match:
        raise ValueError(f"Could not parse year from file name: {path.name}")
    return int(match.group(1))


def _mask_nodata(values: np.ndarray) -> np.ndarray:
    masked = values.astype(np.float32, copy=True)
    masked[np.isclose(masked, NDTI_NODATA_VALUE, atol=1e-6)] = np.nan
    return masked


def build_ndti_annual_station_proxy(
    data_root: str | Path,
    output_dir: str | Path,
    longitude: float,
    latitude: float,
    ndti_dir: str | Path | None = None,
    window_radius: int = 1,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    ndti_root = resolve_ndti_dir(data_root=data_root, ndti_dir=ndti_dir)
    output_dir = ensure_dir(output_dir)

    tif_paths = sorted(ndti_root.glob("turbidity_[0-9][0-9][0-9][0-9].tif"))
    if not tif_paths:
        raise FileNotFoundError(f"No annual NDTI GeoTIFF found under {ndti_root}")

    rows: list[dict[str, Any]] = []
    raster_summaries: list[dict[str, Any]] = []

    for tif_path in tif_paths:
        year = _extract_year(tif_path)
        array, meta = _load_tiff_array(tif_path)
        array = _mask_nodata(array)
        col = int((float(longitude) - meta["origin_x"]) / meta["pixel_size_x"])
        row = int((meta["origin_y"] - float(latitude)) / meta["pixel_size_y"])

        in_bounds = (
            0 <= row < meta["height"]
            and 0 <= col < meta["width"]
            and meta["bounds"]["xmin"] <= float(longitude) <= meta["bounds"]["xmax"]
            and meta["bounds"]["ymin"] <= float(latitude) <= meta["bounds"]["ymax"]
        )
        if not in_bounds:
            continue

        r0 = max(0, row - window_radius)
        r1 = min(meta["height"], row + window_radius + 1)
        c0 = max(0, col - window_radius)
        c1 = min(meta["width"], col + window_radius + 1)
        window = array[r0:r1, c0:c1]

        rows.append(
            {
                "year": year,
                "ndti_station_pixel": float(array[row, col]),
                "ndti_station_3x3_mean": float(np.nanmean(window)),
                "ndti_station_3x3_std": float(np.nanstd(window)),
                "station_row": int(row),
                "station_col": int(col),
                "source_tif": str(tif_path),
            }
        )
        raster_summaries.append(
            {
                "year": year,
                "file": str(tif_path),
                "bounds": meta["bounds"],
                "crs": meta["crs"],
                "pixel_size_x": float(meta["pixel_size_x"]),
                "pixel_size_y": float(meta["pixel_size_y"]),
                "description": meta["description"],
            }
        )

    annual_df = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    if annual_df.empty:
        raise ValueError("Station location did not overlap any NDTI raster.")

    annual_path = Path(output_dir) / DEFAULT_NDTI_FILENAME
    annual_df.to_csv(annual_path, index=False, encoding="utf-8-sig")

    summary = {
        "ndti_root": str(ndti_root),
        "output_csv": str(annual_path),
        "longitude": float(longitude),
        "latitude": float(latitude),
        "available_years": annual_df["year"].astype(int).tolist(),
        "year_count": int(len(annual_df)),
        "window_radius": int(window_radius),
        "raster_summaries": raster_summaries,
    }
    save_json(summary, Path(output_dir) / DEFAULT_NDTI_SUMMARY)
    return annual_df, summary


def expand_ndti_annual_to_daily(
    dates: pd.Series,
    annual_df: pd.DataFrame,
) -> pd.DataFrame:
    daily_df = pd.DataFrame({"date": pd.to_datetime(dates).sort_values().unique()})
    daily_df["year"] = daily_df["date"].dt.year
    annual_features = annual_df.rename(
        columns={
            "ndti_station_pixel": "ndti_annual_pixel",
            "ndti_station_3x3_mean": "ndti_annual_proxy",
            "ndti_station_3x3_std": "ndti_annual_local_std",
        }
    )[
        [
            "year",
            "ndti_annual_pixel",
            "ndti_annual_proxy",
            "ndti_annual_local_std",
        ]
    ]
    daily_df = daily_df.merge(annual_features, on="year", how="left")
    return daily_df.drop(columns=["year"])


def load_or_build_ndti_daily_proxy(
    data_root: str | Path,
    output_dir: str | Path,
    station_meta: dict[str, Any],
    dates: pd.Series,
    ndti_dir: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    annual_df, summary = build_ndti_annual_station_proxy(
        data_root=data_root,
        output_dir=output_dir,
        longitude=float(station_meta["longitude"]),
        latitude=float(station_meta["latitude"]),
        ndti_dir=ndti_dir,
    )
    daily_df = expand_ndti_annual_to_daily(dates=dates, annual_df=annual_df)
    daily_path = Path(output_dir) / "ndti_daily_proxy.csv"
    daily_df.to_csv(daily_path, index=False, encoding="utf-8-sig")
    summary = {
        **summary,
        "daily_proxy_csv": str(daily_path),
        "daily_rows": int(len(daily_df)),
    }
    save_json(summary, Path(output_dir) / DEFAULT_NDTI_SUMMARY)
    return daily_df, summary
