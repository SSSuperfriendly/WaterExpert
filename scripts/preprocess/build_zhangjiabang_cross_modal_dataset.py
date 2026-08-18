from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.vision import extract_visual_transformer_features


DEFAULT_FIELD_MONITORING_PATH = PROJECT_ROOT / "data" / "raw" / "zhangjiabang_field_monitoring.xlsx"
DEFAULT_UAV_ROOT = PROJECT_ROOT / "data" / "raw" / "zhangjiabang_uav"
DEFAULT_PROXY_PATH = (
    PROJECT_ROOT / "data" / "proxy" / "zhangjiabang_proxy" / "zhangjiabang_proxy_daily.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "zhangjiabang_cross_modal"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv"}
SUMMARY_HEADERS = {"指标名称", "指标值", "误差"}
RAW_MEASUREMENT_HEADERS = {"透明度", "浊度", "DO", "EC", "ORP", "pH", "温度"}

METRIC_NAME_MAP = {
    "透明度（m）": "secchi_depth_m",
    "透明度": "secchi_depth_m",
    "浊度（NTU）": "turbidity_ntu",
    "浊度": "turbidity_ntu",
    "温度（℃）": "water_temp_c",
    "温度": "water_temp_c",
    "pH": "ph",
    "ORP（mV）": "orp_mv",
    "ORP": "orp_mv",
    "DO（mg/L）": "dissolved_oxygen_mg_l",
    "DO": "dissolved_oxygen_mg_l",
    "EC(us/cm)": "conductivity_us_cm",
    "EC": "conductivity_us_cm",
    "chl-a(mg/L)": "chlorophyll_a_mg_l",
    "chla": "chlorophyll_a_mg_l",
    "chl-b(mg/L)": "chlorophyll_b_mg_l",
    "chlb": "chlorophyll_b_mg_l",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Zhangjiabang UAV visual features and cross-modal daily dataset."
    )
    parser.add_argument("--field-monitoring", type=Path, default=DEFAULT_FIELD_MONITORING_PATH)
    parser.add_argument("--uav-root", type=Path, default=DEFAULT_UAV_ROOT)
    parser.add_argument("--proxy-daily", type=Path, default=DEFAULT_PROXY_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--video-frame-count",
        type=int,
        default=5,
        help="Representative frames to sample from each video.",
    )
    parser.add_argument(
        "--thumbnail-max-size",
        type=int,
        default=640,
        help="Maximum width/height for generated preview images.",
    )
    return parser.parse_args()


def _clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _to_float(value: Any) -> float | None:
    try:
        if value is None or _clean_text(value) == "":
            return None
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return numeric


def _date_from_text(text: str, *, default_year: int = 2026) -> str | None:
    match = re.search(r"(?:(20\d{2})[.\-/年])?\s*(\d{1,2})[.\-/月]\s*(\d{1,2})", text)
    if not match:
        return None
    year = int(match.group(1) or default_year)
    month = int(match.group(2))
    day = int(match.group(3))
    return f"{year:04d}-{month:02d}-{day:02d}"


def _normalize_metric_name(name: str) -> str:
    return METRIC_NAME_MAP.get(name, name)


def _find_summary_blocks(raw: pd.DataFrame, sheet_name: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    rows, cols = raw.shape
    for row_idx in range(rows):
        for col_idx in range(cols - 2):
            values = {_clean_text(raw.iat[row_idx, col_idx + offset]) for offset in range(3)}
            if SUMMARY_HEADERS.issubset(values):
                time_text = ""
                place_text = ""
                if row_idx >= 2:
                    time_text = _clean_text(raw.iat[row_idx - 2, col_idx + 1])
                    place_text = _clean_text(raw.iat[row_idx - 1, col_idx + 1])
                sample_date = _date_from_text(time_text) or _date_from_text(sheet_name)
                metrics: dict[str, float | str | None] = {}
                errors: dict[str, float | None] = {}
                cursor = row_idx + 1
                while cursor < rows:
                    metric_name = _clean_text(raw.iat[cursor, col_idx])
                    if not metric_name or metric_name in SUMMARY_HEADERS:
                        break
                    value = _to_float(raw.iat[cursor, col_idx + 1])
                    error = _to_float(raw.iat[cursor, col_idx + 2])
                    normalized = _normalize_metric_name(metric_name)
                    metrics[normalized] = value
                    errors[f"{normalized}_error"] = error
                    cursor += 1
                if sample_date and metrics:
                    blocks.append(
                        {
                            "sheet_name": sheet_name,
                            "sample_date": sample_date,
                            "sample_location": place_text,
                            **metrics,
                            **errors,
                        }
                    )
    return blocks


def _find_raw_replicate_blocks(
    raw: pd.DataFrame,
    sheet_name: str,
    *,
    fallback_date: str | None = None,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    rows, cols = raw.shape
    for row_idx in range(rows):
        for col_idx in range(cols):
            value = _clean_text(raw.iat[row_idx, col_idx])
            if value != "透明度":
                continue
            headers = [_clean_text(raw.iat[row_idx, c]) for c in range(col_idx, min(cols, col_idx + 7))]
            if not RAW_MEASUREMENT_HEADERS.issubset(set(headers)):
                continue
            date = _date_from_text(sheet_name) or fallback_date
            if not date:
                continue
            header_positions = {header: col_idx + idx for idx, header in enumerate(headers) if header}
            replicate_idx = 1
            cursor = row_idx + 1
            while cursor < rows:
                if all(_to_float(raw.iat[cursor, col]) is None for col in header_positions.values()):
                    break
                row: dict[str, Any] = {
                    "sheet_name": sheet_name,
                    "sample_date": date,
                    "replicate_index": replicate_idx,
                    "row_type": "raw_replicate"
                    if replicate_idx <= 3
                    else ("mean" if replicate_idx == 4 else "error"),
                }
                for header, col in header_positions.items():
                    row[_normalize_metric_name(header)] = _to_float(raw.iat[cursor, col])
                blocks.append(row)
                replicate_idx += 1
                cursor += 1
    return blocks


def parse_field_monitoring_workbook(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    workbook = pd.ExcelFile(path)
    summary_rows: list[dict[str, Any]] = []
    replicate_rows: list[dict[str, Any]] = []
    previous_date: str | None = None
    for sheet_name in workbook.sheet_names:
        raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
        if raw.empty:
            continue
        sheet_summary_rows = _find_summary_blocks(raw, sheet_name)
        summary_rows.extend(sheet_summary_rows)
        sheet_date = (
            sheet_summary_rows[0].get("sample_date")
            if sheet_summary_rows
            else _date_from_text(sheet_name)
        )
        if sheet_date:
            previous_date = str(sheet_date)
        replicate_rows.extend(
            _find_raw_replicate_blocks(raw, sheet_name, fallback_date=previous_date)
        )

    summary = pd.DataFrame(summary_rows)
    if not summary.empty:
        summary = summary.drop_duplicates(subset=["sample_date", "sample_location"], keep="first")
        summary = summary.sort_values(["sample_date", "sample_location"]).reset_index(drop=True)

    replicates = pd.DataFrame(replicate_rows)
    if not replicates.empty:
        replicates = replicates.sort_values(["sample_date", "sheet_name", "replicate_index"]).reset_index(drop=True)
    return summary, replicates


def _date_from_asset_path(path: Path, uav_root: Path) -> str | None:
    try:
        relative = path.relative_to(uav_root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    return _date_from_text(relative.parts[0])


def _asset_site_role(path: Path, uav_root: Path) -> str:
    try:
        relative = path.relative_to(uav_root)
    except ValueError:
        return "unknown"
    first_part = relative.parts[0] if relative.parts else ""
    if first_part.startswith("2026."):
        return "zhangjiabang_target"
    if first_part in {"7.31", "8.3"}:
        return "chenxing_sanlu_auxiliary"
    return "unknown"


def _field_site_role(location: Any) -> str:
    text = _clean_text(location)
    if "\u5f20\u5bb6\u6d5c" in text:
        return "zhangjiabang_target"
    if "\u9648\u884c" in text or "\u4e09\u9c81\u6cb3" in text:
        return "chenxing_sanlu_auxiliary"
    return "other_field_site"


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _safe_output_stem(path: Path) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", path.stem)
    return safe[:80].strip("._") or "asset"


def _image_features_rgb(image_rgb: np.ndarray) -> dict[str, Any]:
    if image_rgb.size == 0:
        return {}
    height, width = image_rgb.shape[:2]
    # Center-lower crop reduces sky/building contamination for oblique river UAV shots.
    y0 = int(height * 0.25)
    y1 = int(height * 0.92)
    x0 = int(width * 0.08)
    x1 = int(width * 0.92)
    crop = image_rgb[y0:y1, x0:x1]
    if crop.size == 0:
        crop = image_rgb
    crop_float = crop.astype(np.float32)
    red = crop_float[:, :, 0]
    green = crop_float[:, :, 1]
    blue = crop_float[:, :, 2]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    hue = hsv[:, :, 0].astype(np.float32)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)
    eps = 1e-6
    brightness = float(np.mean(val))
    saturation = float(np.mean(sat))
    green_index = float(np.mean((green - red) / (green + red + eps)))
    brown_yellow_index = float(np.mean(((red + green) / 2 - blue) / (red + green + blue + eps)))
    dark_water_ratio = float(np.mean((val < 95) & (sat > 20)))
    high_glare_ratio = float(np.mean((val > 225) & (sat < 45)))
    vegetation_like_ratio = float(np.mean((hue >= 35) & (hue <= 95) & (sat > 45)))
    turbidity_visual_proxy = float(brown_yellow_index * (1 - high_glare_ratio))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return {
        "image_width": int(width),
        "image_height": int(height),
        "brightness_mean": brightness,
        "saturation_mean": saturation,
        "red_mean": float(np.mean(red)),
        "green_mean": float(np.mean(green)),
        "blue_mean": float(np.mean(blue)),
        "green_index": green_index,
        "brown_yellow_index": brown_yellow_index,
        "dark_water_ratio": dark_water_ratio,
        "high_glare_ratio": high_glare_ratio,
        "vegetation_like_ratio": vegetation_like_ratio,
        "turbidity_visual_proxy": turbidity_visual_proxy,
        "sharpness_laplacian": sharpness,
    }


def _write_thumbnail(image_rgb: np.ndarray, output_path: Path, max_size: int) -> None:
    image = Image.fromarray(image_rgb)
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=82)


def _read_image_rgb(path: Path) -> np.ndarray:
    Image.MAX_IMAGE_PIXELS = None
    image = Image.open(path)
    image = ImageOps.exif_transpose(image).convert("RGB")
    return np.asarray(image)


def _process_image_asset(path: Path, preview_dir: Path, max_size: int) -> dict[str, Any]:
    image_rgb = _read_image_rgb(path)
    preview_path = preview_dir / f"{_safe_output_stem(path)}.jpg"
    _write_thumbnail(image_rgb, preview_path, max_size)
    features = {
        **_image_features_rgb(image_rgb),
        **extract_visual_transformer_features(image_rgb),
    }
    return {
        **features,
        "preview_path": _relative(preview_path),
        "frame_count": None,
        "fps": None,
        "duration_seconds": None,
        "representative_frame_paths": "",
    }


def _sample_frame_indices(frame_count: int, sample_count: int) -> list[int]:
    if frame_count <= 0:
        return []
    if frame_count <= sample_count:
        return list(range(frame_count))
    return sorted({int(round(idx)) for idx in np.linspace(0, frame_count - 1, sample_count + 2)[1:-1]})


def _process_video_asset(path: Path, frames_dir: Path, max_size: int, sample_count: int) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {
            "preview_path": "",
            "frame_count": None,
            "fps": None,
            "duration_seconds": None,
            "representative_frame_paths": "",
            "video_opened": False,
        }
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps if fps else None
    frame_features: list[dict[str, Any]] = []
    frame_paths: list[str] = []
    video_frame_dir = frames_dir / _safe_output_stem(path)
    for ordinal, frame_idx in enumerate(_sample_frame_indices(frame_count, sample_count), start=1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame_bgr = cap.read()
        if not ok:
            continue
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        frame_path = video_frame_dir / f"frame_{ordinal:02d}.jpg"
        _write_thumbnail(frame_rgb, frame_path, max_size)
        features = {
            **_image_features_rgb(frame_rgb),
            **extract_visual_transformer_features(frame_rgb),
        }
        features["sampled_frame_index"] = frame_idx
        frame_features.append(features)
        frame_paths.append(_relative(frame_path))
    cap.release()

    aggregated: dict[str, Any] = {
        "image_width": width,
        "image_height": height,
        "frame_count": frame_count,
        "fps": fps,
        "duration_seconds": duration,
        "video_opened": True,
        "representative_frame_paths": ";".join(frame_paths),
        "preview_path": frame_paths[0] if frame_paths else "",
    }
    if frame_features:
        numeric_keys = [
            key
            for key, value in frame_features[0].items()
            if isinstance(value, (int, float)) and key not in {"image_width", "image_height", "sampled_frame_index"}
        ]
        for key in numeric_keys:
            values = [float(item[key]) for item in frame_features if item.get(key) is not None]
            if values:
                aggregated[key] = float(np.mean(values))
                aggregated[f"{key}_std"] = float(np.std(values))
        aggregated["sampled_frame_count"] = len(frame_features)
    else:
        aggregated["sampled_frame_count"] = 0
    return aggregated


def build_uav_asset_index(
    *,
    uav_root: Path,
    output_dir: Path,
    video_frame_count: int,
    thumbnail_max_size: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    preview_dir = output_dir / "thumbnails"
    frames_dir = output_dir / "video_frames"
    for path in sorted(uav_root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in IMAGE_SUFFIXES and suffix not in VIDEO_SUFFIXES:
            continue
        sample_date = _date_from_asset_path(path, uav_root)
        media_type = "image" if suffix in IMAGE_SUFFIXES else "video"
        site_role = _asset_site_role(path, uav_root)
        base = {
            "asset_id": f"uav_{sample_date or 'unknown'}_{_safe_output_stem(path)}",
            "sample_date": sample_date,
            "sample_site_role": site_role,
            "media_type": media_type,
            "file_name": path.name,
            "source_path": _relative(path),
            "file_size_bytes": path.stat().st_size,
            "file_modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        }
        if media_type == "image":
            media_features = _process_image_asset(path, preview_dir, thumbnail_max_size)
        else:
            media_features = _process_video_asset(path, frames_dir, thumbnail_max_size, video_frame_count)
        rows.append({**base, **media_features})
    return pd.DataFrame(rows).sort_values(["sample_date", "media_type", "file_name"]).reset_index(drop=True)


def aggregate_visual_features(assets: pd.DataFrame) -> pd.DataFrame:
    if assets.empty:
        return pd.DataFrame()
    numeric_columns = [
        column
        for column in assets.columns
        if column
        not in {
            "asset_id",
            "sample_date",
            "media_type",
            "file_name",
            "source_path",
            "file_modified_at",
            "preview_path",
            "representative_frame_paths",
        }
        and pd.api.types.is_numeric_dtype(assets[column])
    ]
    rows: list[dict[str, Any]] = []
    for sample_date, group in assets.groupby("sample_date", dropna=False):
        row: dict[str, Any] = {
            "sample_date": sample_date,
            "sample_site_role": (
                group["sample_site_role"].mode(dropna=True).iloc[0]
                if "sample_site_role" in group and not group["sample_site_role"].dropna().empty
                else "unknown"
            ),
            "uav_asset_count": int(len(group)),
            "uav_image_count": int((group["media_type"] == "image").sum()),
            "uav_video_count": int((group["media_type"] == "video").sum()),
            "uav_total_size_bytes": int(group["file_size_bytes"].sum()),
            "uav_preview_paths": ";".join(group["preview_path"].dropna().astype(str).head(6)),
        }
        for column in numeric_columns:
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            if not values.empty:
                row[f"uav_{column}_mean"] = float(values.mean())
                row[f"uav_{column}_max"] = float(values.max())
                row[f"uav_{column}_min"] = float(values.min())
        rows.append(row)
    return pd.DataFrame(rows).sort_values("sample_date").reset_index(drop=True)


def _zhangjiabang_only(field_summary: pd.DataFrame) -> pd.DataFrame:
    if field_summary.empty or "sample_location" not in field_summary:
        return field_summary
    mask = field_summary["sample_location"].fillna("").astype(str).str.contains("张家浜", regex=False)
    filtered = field_summary[mask].copy()
    return filtered if not filtered.empty else field_summary.copy()


def _target_field_only(field_summary: pd.DataFrame) -> pd.DataFrame:
    if field_summary.empty or "sample_location" not in field_summary:
        return field_summary
    mask = field_summary["sample_location"].apply(_field_site_role).eq("zhangjiabang_target")
    filtered = field_summary[mask].copy()
    return filtered if not filtered.empty else field_summary.copy()


def _attach_nearest_field_labels(
    visual_daily: pd.DataFrame,
    field: pd.DataFrame,
    max_days: int = 7,
) -> pd.DataFrame:
    if visual_daily.empty or field.empty:
        result = visual_daily.copy()
        result["label_alignment"] = "no_field_label"
        result["label_offset_days"] = None
        result["field_sample_date"] = ""
        return result

    visual = visual_daily.copy()
    field = field.copy()
    visual["sample_date_dt"] = pd.to_datetime(visual["sample_date"])
    field["field_sample_date"] = field["sample_date"]
    field["sample_date_dt"] = pd.to_datetime(field["sample_date"])
    field["field_site_role"] = field["sample_location"].apply(_field_site_role)
    field = field.sort_values("sample_date_dt")

    rows: list[dict[str, Any]] = []
    for _, visual_row in visual.iterrows():
        site_role = visual_row.get("sample_site_role", "unknown")
        candidate_field = field
        if site_role in {"zhangjiabang_target", "chenxing_sanlu_auxiliary"}:
            candidate_field = field[field["field_site_role"].eq(site_role)]
        if candidate_field.empty:
            candidate_field = field
        deltas = (candidate_field["sample_date_dt"] - visual_row["sample_date_dt"]).abs().dt.days
        if deltas.empty or int(deltas.min()) > max_days:
            row = visual_row.drop(labels=["sample_date_dt"]).to_dict()
            row["label_alignment"] = "no_field_label"
            row["label_offset_days"] = None
            row["field_sample_date"] = ""
            row["field_site_role"] = ""
            rows.append(row)
            continue
        nearest_index = deltas.idxmin()
        nearest = candidate_field.loc[nearest_index].drop(labels=["sample_date_dt"]).to_dict()
        offset = int((pd.to_datetime(nearest["field_sample_date"]) - visual_row["sample_date_dt"]).days)
        row = visual_row.drop(labels=["sample_date_dt"]).to_dict()
        for key, value in nearest.items():
            if key == "sample_date":
                continue
            row[key] = value
        row["label_offset_days"] = offset
        abs_offset = abs(offset)
        if abs_offset == 0:
            row["label_alignment"] = "exact_same_day"
        elif abs_offset <= 1:
            row["label_alignment"] = "near_day"
        else:
            row["label_alignment"] = "same_week_context"
        row["label_confidence"] = float(math.exp(-abs_offset / 3))
        rows.append(row)
    return pd.DataFrame(rows)


def _month_part(day: int) -> str:
    if day <= 10:
        return "early"
    if day <= 20:
        return "middle"
    return "late"


def _historical_proxy_context(proxy: pd.DataFrame, sample_dates: pd.Series) -> pd.DataFrame:
    if proxy.empty or "date" not in proxy:
        return pd.DataFrame({"sample_date": sample_dates.astype(str)})
    proxy = proxy.copy()
    proxy["date"] = pd.to_datetime(proxy["date"], errors="coerce")
    proxy = proxy[proxy["date"].notna()].copy()
    if proxy.empty:
        return pd.DataFrame({"sample_date": sample_dates.astype(str)})
    proxy["month"] = proxy["date"].dt.month
    proxy["month_part"] = proxy["date"].dt.day.apply(_month_part)
    numeric_fields = [
        field
        for field in [
            "turbidity",
            "secchi_depth_sd_m",
            "water_temp",
            "ph",
            "dissolved_oxygen",
            "conductivity",
            "weather_pressure",
            "weather_air_temp",
            "weather_humidity",
            "weather_precipitation",
            "weather_wind_speed",
            "weather_wind_dir",
        ]
        if field in proxy.columns
    ]
    rows: list[dict[str, Any]] = []
    for sample_date in pd.to_datetime(sample_dates, errors="coerce"):
        if pd.isna(sample_date):
            rows.append({"sample_date": ""})
            continue
        candidates = proxy[
            (proxy["month"] == sample_date.month)
            & (proxy["month_part"] == _month_part(int(sample_date.day)))
        ]
        if candidates.empty:
            candidates = proxy[proxy["month"] == sample_date.month]
        row: dict[str, Any] = {
            "sample_date": sample_date.strftime("%Y-%m-%d"),
            "historical_proxy_match_scope": "same_month_part"
            if not candidates.empty
            else "unmatched",
            "historical_proxy_rows": int(len(candidates)),
        }
        for field in numeric_fields:
            values = pd.to_numeric(candidates[field], errors="coerce").dropna()
            if values.empty:
                continue
            row[f"historical_proxy_{field}_median"] = float(values.median())
            row[f"historical_proxy_{field}_iqr"] = float(values.quantile(0.75) - values.quantile(0.25))
        rows.append(row)
    return pd.DataFrame(rows)


def build_cross_modal_dataset(
    field_summary: pd.DataFrame,
    visual_daily: pd.DataFrame,
    proxy_path: Path,
) -> pd.DataFrame:
    field = field_summary.copy()
    cross_modal = _attach_nearest_field_labels(visual_daily, field, max_days=7)

    if proxy_path.exists():
        proxy = pd.read_csv(proxy_path, encoding="utf-8-sig")
        proxy_columns = [
            column
            for column in [
                "date",
                "weather_pressure",
                "weather_air_temp",
                "weather_humidity",
                "weather_precipitation",
                "weather_wind_speed",
                "weather_wind_dir",
            ]
            if column in proxy.columns
        ]
        if proxy_columns:
            proxy_subset = proxy[proxy_columns].rename(columns={"date": "sample_date"})
            cross_modal = cross_modal.merge(proxy_subset, on="sample_date", how="left")
            historical_proxy = _historical_proxy_context(proxy, cross_modal["sample_date"])
            cross_modal = cross_modal.merge(historical_proxy, on="sample_date", how="left")

    if not cross_modal.empty:
        cross_modal["has_field_monitoring_label"] = cross_modal["turbidity_ntu"].notna() if "turbidity_ntu" in cross_modal else False
        cross_modal["has_uav_visual_features"] = cross_modal["uav_asset_count"].fillna(0).astype(float) > 0
        conditions = [
            cross_modal["has_field_monitoring_label"]
            & cross_modal["has_uav_visual_features"]
            & cross_modal["label_alignment"].eq("exact_same_day"),
            cross_modal["has_field_monitoring_label"]
            & cross_modal["has_uav_visual_features"]
            & cross_modal["label_alignment"].eq("near_day"),
            cross_modal["has_field_monitoring_label"] & cross_modal["has_uav_visual_features"],
        ]
        choices = [
            "strong_supervised_cross_modal_sample",
            "near_day_supervised_cross_modal_sample",
            "weak_temporal_context_cross_modal_sample",
        ]
        cross_modal["fusion_readiness"] = np.select(
            conditions,
            choices,
            default="uav_only_or_unlabeled_sample",
        )
    return cross_modal.sort_values("sample_date").reset_index(drop=True)


def write_outputs(
    *,
    output_dir: Path,
    field_summary: pd.DataFrame,
    field_replicates: pd.DataFrame,
    asset_index: pd.DataFrame,
    visual_daily: pd.DataFrame,
    cross_modal: pd.DataFrame,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "field_summary_csv": output_dir / "field_monitoring_summary.csv",
        "field_replicates_csv": output_dir / "field_monitoring_replicates.csv",
        "uav_asset_index_csv": output_dir / "uav_asset_index.csv",
        "uav_visual_daily_csv": output_dir / "uav_visual_daily_features.csv",
        "cross_modal_daily_csv": output_dir / "zhangjiabang_cross_modal_daily.csv",
        "summary_json": output_dir / "zhangjiabang_cross_modal_summary.json",
    }
    csv_options = {
        "index": False,
        "encoding": "utf-8-sig",
        "lineterminator": "\n",
    }
    field_summary.to_csv(paths["field_summary_csv"], **csv_options)
    field_replicates.to_csv(paths["field_replicates_csv"], **csv_options)
    asset_index.to_csv(paths["uav_asset_index_csv"], **csv_options)
    visual_daily.to_csv(paths["uav_visual_daily_csv"], **csv_options)
    cross_modal.to_csv(paths["cross_modal_daily_csv"], **csv_options)

    ready_count = int(
        cross_modal.get("fusion_readiness", pd.Series(dtype=str))
        .astype(str)
        .str.contains("supervised|weak_temporal", regex=True)
        .sum()
    ) if not cross_modal.empty else 0
    strong_count = int((cross_modal.get("fusion_readiness") == "strong_supervised_cross_modal_sample").sum()) if not cross_modal.empty else 0
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site": "张家浜",
        "modality_status": {
            "field_monitoring": "parsed",
            "uav_images": "indexed_and_featurized",
            "uav_videos": "sampled_frames_and_featurized",
            "visual_transformer": "patch_tokens_encoded",
            "proxy_weather": "joined_when_dates_overlap",
        },
        "counts": {
            "field_monitoring_rows": int(len(field_summary)),
            "field_monitoring_zhangjiabang_rows": int(len(_target_field_only(field_summary))),
            "field_replicate_rows": int(len(field_replicates)),
            "uav_assets": int(len(asset_index)),
            "uav_images": int((asset_index["media_type"] == "image").sum()) if not asset_index.empty else 0,
            "uav_videos": int((asset_index["media_type"] == "video").sum()) if not asset_index.empty else 0,
            "uav_dates": int(asset_index["sample_date"].nunique()) if not asset_index.empty else 0,
            "cross_modal_rows": int(len(cross_modal)),
            "supervised_cross_modal_rows": ready_count,
            "strong_same_day_cross_modal_rows": strong_count,
        },
        "date_ranges": {
            "uav": {
                "start": str(asset_index["sample_date"].min()) if not asset_index.empty else "",
                "end": str(asset_index["sample_date"].max()) if not asset_index.empty else "",
            },
            "field_monitoring": {
                "start": str(field_summary["sample_date"].min()) if not field_summary.empty else "",
                "end": str(field_summary["sample_date"].max()) if not field_summary.empty else "",
            },
            "cross_modal": {
                "start": str(cross_modal["sample_date"].min()) if not cross_modal.empty else "",
                "end": str(cross_modal["sample_date"].max()) if not cross_modal.empty else "",
            },
        },
        "supervised_dates": (
            cross_modal.loc[
                cross_modal.get("fusion_readiness")
                .astype(str)
                .str.contains("supervised|weak_temporal", regex=True),
                "sample_date",
            ]
            .dropna()
            .astype(str)
            .tolist()
            if not cross_modal.empty and "fusion_readiness" in cross_modal
            else []
        ),
        "outputs": {key: _relative(path) for key, path in paths.items()},
        "fusion_route": [
            "Field monitoring provides measured turbidity, transparency, water temperature, pH, ORP, DO, EC, and chlorophyll labels.",
            "UAV images and videos are converted into date-indexed visual assets, thumbnails, representative frames, color/texture quality features, and 32-dimensional visual Transformer embeddings.",
            "The daily fusion table aligns UAV visual features with field monitoring labels and proxy weather features by sample date.",
            "Current model-level fusion uses the generated daily table as the tabular bridge: interpretable visual proxies support diagnosis, while Transformer embeddings provide the visual representation branch for downstream MSCIM fusion.",
        ],
    }
    paths["summary_json"].write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    args = parse_args()
    if not args.field_monitoring.exists():
        raise FileNotFoundError(args.field_monitoring)
    if not args.uav_root.exists():
        raise FileNotFoundError(args.uav_root)

    output_dir = args.output_dir
    if output_dir.exists():
        # Keep this script reproducible without leaving stale thumbnails from renamed assets.
        for child in ["thumbnails", "video_frames"]:
            path = output_dir / child
            if path.exists():
                shutil.rmtree(path)

    field_summary, field_replicates = parse_field_monitoring_workbook(args.field_monitoring)
    asset_index = build_uav_asset_index(
        uav_root=args.uav_root,
        output_dir=output_dir,
        video_frame_count=max(1, args.video_frame_count),
        thumbnail_max_size=max(120, args.thumbnail_max_size),
    )
    visual_daily = aggregate_visual_features(asset_index)
    cross_modal = build_cross_modal_dataset(field_summary, visual_daily, args.proxy_daily)
    summary = write_outputs(
        output_dir=output_dir,
        field_summary=field_summary,
        field_replicates=field_replicates,
        asset_index=asset_index,
        visual_daily=visual_daily,
        cross_modal=cross_modal,
    )
    counts = summary["counts"]
    print(f"Parsed field monitoring rows: {counts['field_monitoring_rows']}")
    print(f"Indexed UAV assets: {counts['uav_assets']} ({counts['uav_images']} images, {counts['uav_videos']} videos)")
    print(f"Built cross-modal rows: {counts['cross_modal_rows']}")
    print(f"Supervised cross-modal rows: {counts['supervised_cross_modal_rows']}")
    print(f"Summary: {summary['outputs']['summary_json']}")


if __name__ == "__main__":
    main()
