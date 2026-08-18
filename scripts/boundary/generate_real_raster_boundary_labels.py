from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from water_ai.data.multimodal_builder import build_multimodal_dataset
from water_ai.utils.io import ensure_dir, load_yaml, save_json


GWP_URL_TEMPLATE = (
    "https://download.geoservice.dlr.de/GWP/files/daily/"
    "{year}/{month:02d}/{day:02d}/GWP.OSWF.DAILY.{year}{month:02d}{day:02d}.v1.tif"
)
SWIM_STAC_SEARCH_URL = "https://geoservice.dlr.de/eoc/ogc/stac/v1/search"


def resolve_repo_path(path_value: str | Path | None) -> str | None:
    if path_value is None:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return str(path)
    return str((PROJECT_ROOT / path).resolve())


def _load_base_dataset(config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    hydrodynamics_config = config.get("hydrodynamics", {})
    ndti_config = config.get("ndti", {})
    dataset_df, dataset_summary = build_multimodal_dataset(
        data_root=resolve_repo_path(config["data_root"]),
        water_pattern=config["water_pattern"],
        weather_filename=config["weather_filename"],
        output_dir=resolve_repo_path(config.get("output_dir", "outputs")),
        hydrodynamics_enabled=bool(hydrodynamics_config.get("enabled", False)),
        hydrodynamics_source_path=resolve_repo_path(hydrodynamics_config.get("source_path")),
        hydrodynamics_wide_path=resolve_repo_path(hydrodynamics_config.get("wide_path")),
        hydrodynamics_output_dir=resolve_repo_path(hydrodynamics_config.get("output_dir")),
        ndti_enabled=bool(ndti_config.get("enabled", False)),
        ndti_dir=resolve_repo_path(ndti_config.get("source_dir")),
        ndti_output_dir=resolve_repo_path(ndti_config.get("output_dir")),
        boundary_config={"enabled": False},
    )
    return dataset_df, dataset_summary


def _read_json_url(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if payload is None:
        request = urllib.request.Request(url)
    else:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_gwp_mask(
    timestamp: pd.Timestamp,
    center_lon: float,
    center_lat: float,
    half_size_deg: float,
) -> tuple[pd.Timestamp, np.ndarray, float]:
    url = GWP_URL_TEMPLATE.format(
        year=timestamp.year,
        month=timestamp.month,
        day=timestamp.day,
    )
    with rasterio.Env(CPL_CURL_VERIFY_SSL="NO", GDAL_HTTP_UNSAFESSL="YES"):
        with rasterio.open(url) as src:
            window = from_bounds(
                center_lon - half_size_deg,
                center_lat - half_size_deg,
                center_lon + half_size_deg,
                center_lat + half_size_deg,
                src.transform,
            )
            array = src.read(1, window=window, boundless=True)
    valid_mask = array != 255
    if valid_mask.sum() == 0:
        raise RuntimeError(f"No valid GWP pixels found for {timestamp.date()}.")
    water_mask = ((array == 1) & valid_mask).astype(np.uint8)
    return timestamp, water_mask, float(valid_mask.mean())


def _select_sample_dates(dataset_dates: pd.Series, stride_days: int) -> list[pd.Timestamp]:
    unique_dates = pd.to_datetime(dataset_dates).drop_duplicates().sort_values().reset_index(drop=True)
    sampled_dates = unique_dates.iloc[:: max(1, stride_days)].tolist()
    if sampled_dates[-1] != unique_dates.iloc[-1]:
        sampled_dates.append(unique_dates.iloc[-1])
    return sampled_dates


def _augment_dense_tail_dates(
    sampled_dates: list[pd.Timestamp],
    dataset_dates: pd.Series,
    dense_tail_days: int,
) -> list[pd.Timestamp]:
    unique_dates = pd.to_datetime(dataset_dates).drop_duplicates().sort_values().reset_index(drop=True)
    if dense_tail_days <= 0:
        return sampled_dates
    tail_dates = unique_dates.iloc[-min(len(unique_dates), dense_tail_days) :].tolist()
    combined = sorted({*sampled_dates, *tail_dates})
    return combined


def _compute_edge_density(mask: np.ndarray) -> float:
    horizontal = float((mask[:, 1:] != mask[:, :-1]).mean())
    vertical = float((mask[1:, :] != mask[:-1, :]).mean())
    return (horizontal + vertical) / 2.0


def _fetch_swim_catalog(
    center_lon: float,
    center_lat: float,
    half_size_deg: float,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    payload = {
        "collections": ["SWIM_WE"],
        "bbox": [
            center_lon - half_size_deg,
            center_lat - half_size_deg,
            center_lon + half_size_deg,
            center_lat + half_size_deg,
        ],
        "datetime": (
            f"{start_date.strftime('%Y-%m-%dT00:00:00Z')}/"
            f"{end_date.strftime('%Y-%m-%dT23:59:59Z')}"
        ),
        "limit": 200,
    }
    response = _read_json_url(SWIM_STAC_SEARCH_URL, payload=payload)
    rows: list[dict[str, Any]] = []
    for feature in response.get("features", []):
        properties = feature.get("properties", {})
        statistics = properties.get("statistics", {})
        rows.append(
            {
                "item_id": feature.get("id"),
                "date": str(properties.get("datetime", ""))[:10],
                "src_platform": properties.get("src_platform"),
                "valid_pct_scene": statistics.get("valid"),
                "water_pct_scene": statistics.get("water"),
                "mask_href": feature.get("assets", {}).get("data", {}).get("href"),
                "thumbnail_href": feature.get("assets", {}).get("thumbnail", {}).get("href"),
            }
        )
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def main() -> None:
    config = load_yaml(PROJECT_ROOT / "configs" / "default.yaml")
    boundary_config = config.get("boundary_labels", {})
    raster_proxy_config = boundary_config.get("raster_proxy", {})
    output_dir = ensure_dir(resolve_repo_path(config.get("output_dir", "outputs")))
    boundary_output_dir = ensure_dir(output_dir / "boundary")

    dataset_df, dataset_summary = _load_base_dataset(config)
    station_meta = dataset_summary["water_station"]
    center_lon = float(raster_proxy_config.get("center_lon", station_meta["longitude"]))
    center_lat = float(raster_proxy_config.get("center_lat", station_meta["latitude"]))
    half_size_deg = float(raster_proxy_config.get("aoi_half_size_deg", 0.03))
    stride_days = int(raster_proxy_config.get("sampling_stride_days", 7))
    dense_tail_days = int(raster_proxy_config.get("dense_tail_days", 140))
    max_workers = int(raster_proxy_config.get("max_workers", 4))
    label_quantile = float(raster_proxy_config.get("boundary_label_quantile", 0.75))
    minimum_ratio = float(raster_proxy_config.get("boundary_label_min_ratio", 0.015))
    minimum_positive_count = int(raster_proxy_config.get("minimum_positive_count", 18))
    output_path = Path(resolve_repo_path(boundary_config.get(
        "source_path", "data/raw/wusongkou_boundary_labels.csv"
    )))

    sampled_dates = _select_sample_dates(dataset_df["date"], stride_days=stride_days)
    sampled_dates = _augment_dense_tail_dates(
        sampled_dates=sampled_dates,
        dataset_dates=dataset_df["date"],
        dense_tail_days=dense_tail_days,
    )
    masks: list[np.ndarray] = []
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _fetch_gwp_mask,
                timestamp=timestamp,
                center_lon=center_lon,
                center_lat=center_lat,
                half_size_deg=half_size_deg,
            ): timestamp
            for timestamp in sampled_dates
        }
        for future in as_completed(futures):
            timestamp = futures[future]
            try:
                sampled_timestamp, mask, valid_fraction = future.result()
                masks.append(mask)
                records.append(
                    {
                        "date": sampled_timestamp.strftime("%Y-%m-%d"),
                        "valid_fraction": valid_fraction,
                        "water_fraction": float(mask.mean()),
                        "mask": mask,
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "date": timestamp.strftime("%Y-%m-%d"),
                        "error": str(exc),
                    }
                )

    if not records:
        raise RuntimeError("No real raster boundary samples could be loaded.")

    records.sort(key=lambda item: item["date"])
    reference_mask = (np.mean(np.stack(masks, axis=0), axis=0) >= 0.5).astype(np.uint8)
    sampled_df = pd.DataFrame(records)
    sampled_df["boundary_extent_ratio"] = sampled_df["mask"].map(
        lambda mask: float((mask != reference_mask).mean())
    )
    sampled_df["edge_density"] = sampled_df["mask"].map(_compute_edge_density)
    sampled_df["label_source"] = "DLR_GWP_P1D_real_raster_proxy"
    sampled_df["boundary_zone_name"] = "wusongkou_aoi_boundary_proxy"
    threshold = max(
        minimum_ratio,
        float(sampled_df["boundary_extent_ratio"].quantile(label_quantile)),
    )
    sampled_df["boundary_label"] = (
        sampled_df["boundary_extent_ratio"] >= threshold
    ).astype(int)
    if int(sampled_df["boundary_label"].sum()) < minimum_positive_count:
        relaxed_quantile = max(0.60, label_quantile - 0.10)
        threshold = max(
            minimum_ratio,
            float(sampled_df["boundary_extent_ratio"].quantile(relaxed_quantile)),
        )
        sampled_df["boundary_label"] = (
            sampled_df["boundary_extent_ratio"] >= threshold
        ).astype(int)
    sampled_df["label_confidence"] = (
        (
            sampled_df["boundary_extent_ratio"] - threshold
        ).abs()
        / max(threshold, 1e-6)
    ).clip(lower=0.15, upper=1.0)
    sampled_df["notes"] = (
        "Derived from DLR Global WaterPack daily real raster masks within a "
        "station-centered AOI; label denotes boundary-change proxy relative to the "
        "median reference mask, not a manual governance-zone annotation."
    )
    sampled_df = sampled_df.drop(columns=["mask"])

    full_label_df = pd.DataFrame(
        {
            "date": pd.to_datetime(dataset_df["date"]).dt.strftime("%Y-%m-%d"),
            "boundary_label": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "boundary_extent_ratio": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "label_source": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "label_confidence": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "boundary_zone_name": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "notes": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "water_fraction": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "edge_density": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
            "valid_fraction": pd.Series([pd.NA] * len(dataset_df), dtype="object"),
        }
    )
    full_label_df = full_label_df.merge(
        sampled_df,
        on="date",
        how="left",
        suffixes=("", "_sampled"),
    )
    for column in [
        "boundary_label",
        "boundary_extent_ratio",
        "label_source",
        "label_confidence",
        "boundary_zone_name",
        "notes",
        "water_fraction",
        "edge_density",
        "valid_fraction",
    ]:
        sampled_column = f"{column}_sampled"
        if sampled_column in full_label_df.columns:
            full_label_df[column] = full_label_df[sampled_column].combine_first(
                full_label_df[column]
            )
            full_label_df = full_label_df.drop(columns=[sampled_column])

    full_label_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    swim_catalog = _fetch_swim_catalog(
        center_lon=center_lon,
        center_lat=center_lat,
        half_size_deg=max(half_size_deg, 0.08),
        start_date=pd.to_datetime(dataset_df["date"]).min(),
        end_date=pd.to_datetime(dataset_df["date"]).max(),
    )
    if not swim_catalog.empty:
        swim_catalog.to_csv(
            boundary_output_dir / "swim_we_catalog.csv",
            index=False,
            encoding="utf-8-sig",
        )

    summary = {
        "status": "ok",
        "output_path": str(output_path),
        "provider": "DLR_GWP_P1D",
        "label_semantics": (
            "Weekly real-raster boundary-change proxy aligned to the current daily "
            "prototype. Labels reflect AOI water-mask boundary deviation relative to a "
            "median reference mask."
        ),
        "aoi": {
            "center_lon": center_lon,
            "center_lat": center_lat,
            "half_size_deg": half_size_deg,
        },
        "sampled_days": int(len(sampled_df)),
        "dataset_days": int(len(full_label_df)),
        "positive_labeled_days": int(sampled_df["boundary_label"].sum()),
        "label_threshold": threshold,
        "boundary_label_quantile": label_quantile,
        "sampling_stride_days": stride_days,
        "dense_tail_days": dense_tail_days,
        "minimum_positive_count": minimum_positive_count,
        "boundary_extent_ratio_stats": {
            "min": float(sampled_df["boundary_extent_ratio"].min()),
            "median": float(sampled_df["boundary_extent_ratio"].median()),
            "max": float(sampled_df["boundary_extent_ratio"].max()),
        },
        "water_fraction_stats": {
            "min": float(sampled_df["water_fraction"].min()),
            "median": float(sampled_df["water_fraction"].median()),
            "max": float(sampled_df["water_fraction"].max()),
        },
        "failed_days": failures,
        "swim_we_highres_items": int(len(swim_catalog)),
    }
    save_json(summary, boundary_output_dir / "boundary_label_generation_summary.json")
    sampled_df.to_csv(
        boundary_output_dir / "boundary_labeled_samples.csv",
        index=False,
        encoding="utf-8-sig",
    )
    print(f"Saved real raster boundary labels: {output_path}")
    print(
        "Saved boundary label summary: "
        f"{boundary_output_dir / 'boundary_label_generation_summary.json'}"
    )


if __name__ == "__main__":
    main()
