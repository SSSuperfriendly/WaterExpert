from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import Settings


CROSS_MODAL_ROOT = Path("data") / "processed" / "zhangjiabang_cross_modal"
SUMMARY_FILE = CROSS_MODAL_ROOT / "zhangjiabang_cross_modal_summary.json"
ASSET_INDEX_FILE = CROSS_MODAL_ROOT / "uav_asset_index.csv"
CROSS_MODAL_DAILY_FILE = CROSS_MODAL_ROOT / "zhangjiabang_cross_modal_daily.csv"


class CrossModalRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.runtime_root / CROSS_MODAL_ROOT

    def _read_json(self, relative_path: Path) -> dict[str, Any]:
        path = self.settings.runtime_root / relative_path
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_csv(self, relative_path: Path) -> pd.DataFrame:
        path = self.settings.runtime_root / relative_path
        if not path.exists():
            raise FileNotFoundError(path)
        return pd.read_csv(path, encoding="utf-8-sig")

    def _media_url(self, relative_path: str | float | None) -> str:
        if not relative_path or pd.isna(relative_path):
            return ""
        return f"/api/v1/cross-modal/media?path={str(relative_path)}"

    def summary(self) -> dict[str, Any]:
        summary = self._read_json(SUMMARY_FILE)
        assets = self._read_csv(ASSET_INDEX_FILE)
        daily = self._read_csv(CROSS_MODAL_DAILY_FILE)

        preview_assets = []
        for row in assets.head(12).to_dict(orient="records"):
            preview_assets.append(
                {
                    "sample_date": row.get("sample_date", ""),
                    "media_type": row.get("media_type", ""),
                    "file_name": row.get("file_name", ""),
                    "file_size_bytes": row.get("file_size_bytes"),
                    "preview_url": self._media_url(row.get("preview_path")),
                    "frame_count": row.get("frame_count"),
                    "duration_seconds": row.get("duration_seconds"),
                    "turbidity_visual_proxy": row.get("turbidity_visual_proxy"),
                    "sharpness_laplacian": row.get("sharpness_laplacian"),
                }
            )

        daily_columns = [
            column
            for column in [
                "sample_date",
                "field_sample_date",
                "label_alignment",
                "label_offset_days",
                "fusion_readiness",
                "turbidity_ntu",
                "secchi_depth_m",
                "water_temp_c",
                "ph",
                "dissolved_oxygen_mg_l",
                "conductivity_us_cm",
                "uav_asset_count",
                "uav_image_count",
                "uav_video_count",
                "uav_turbidity_visual_proxy_mean",
                "uav_brown_yellow_index_mean",
                "uav_green_index_mean",
                "uav_high_glare_ratio_mean",
                "uav_sharpness_laplacian_mean",
            ]
            if column in daily.columns
        ]
        daily_rows = daily[daily_columns].replace({float("nan"): None}).to_dict(orient="records")
        return {
            **summary,
            "preview_assets": preview_assets,
            "daily_rows": daily_rows,
        }

    def resolve_media_path(self, relative_path: str) -> Path:
        candidate = (self.settings.runtime_root / relative_path).resolve()
        allowed_root = self.root.resolve()
        if not candidate.is_file() or allowed_root not in candidate.parents:
            raise FileNotFoundError(relative_path)
        return candidate
