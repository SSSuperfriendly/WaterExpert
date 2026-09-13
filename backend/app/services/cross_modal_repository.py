from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import Settings
from backend.app.services.artifact_io import read_csv, read_json

CROSS_MODAL_ROOT = Path("data") / "processed" / "zhangjiabang_cross_modal"
RAW_UAV_ROOT = Path("data") / "raw" / "zhangjiabang_uav"
#: A persistent home for the (large, gitignored) source videos. ``var/`` is never
#: touched by ``release.sh``'s rsync, so a video dropped here survives releases.
MEDIA_UAV_ROOT = Path("var") / "media" / "zhangjiabang_uav"
SUMMARY_FILE = CROSS_MODAL_ROOT / "zhangjiabang_cross_modal_summary.json"
ASSET_INDEX_FILE = CROSS_MODAL_ROOT / "uav_asset_index.csv"

#: Media is served only from these roots: the processed artifacts (thumbnails,
#: sliced frames), the raw UAV drop, and the persistent media drop. Anything
#: else is refused.
ALLOWED_MEDIA_ROOTS = (CROSS_MODAL_ROOT, RAW_UAV_ROOT, MEDIA_UAV_ROOT)


class CrossModalRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.runtime_root / CROSS_MODAL_ROOT

    def _read_json(self, relative_path: Path) -> dict[str, Any]:
        return read_json(self.settings.runtime_root / relative_path)

    def _read_csv(self, relative_path: Path) -> pd.DataFrame:
        return read_csv(self.settings.runtime_root / relative_path)

    def _media_url(self, relative_path: str | float | None) -> str:
        if not relative_path or pd.isna(relative_path):
            return ""
        return f"/api/v1/cross-modal/media?path={relative_path!s}"

    def summary(self) -> dict[str, Any]:
        summary = self._read_json(SUMMARY_FILE)
        assets = self._read_csv(ASSET_INDEX_FILE)

        # Stable per-(date, media_type) ordinals over the *full* index, so the
        # preview slice keeps the numbering the UI shows and a raw filename like
        # "7.13-…没拍好.MP4" never has to be the display name.
        sequences: dict[str, int] = {}
        counters: dict[tuple[str, str], int] = {}
        for row in assets.to_dict(orient="records"):
            key = (str(row.get("sample_date", "")), str(row.get("media_type", "")))
            counters[key] = counters.get(key, 0) + 1
            sequences[str(row.get("asset_id", ""))] = counters[key]

        preview_assets = []
        for row in assets.head(12).to_dict(orient="records"):
            asset_id = str(row.get("asset_id", ""))
            media_type = str(row.get("media_type", ""))
            representative_frames = [
                self._media_url(path.strip())
                for path in str(row.get("representative_frame_paths") or "").split(";")
                if path.strip()
            ]
            preview_assets.append(
                {
                    "asset_id": asset_id,
                    "sample_date": row.get("sample_date", ""),
                    "sample_site_role": row.get("sample_site_role", ""),
                    "media_type": media_type,
                    "sequence": sequences.get(asset_id, 1),
                    "file_name": row.get("file_name", ""),
                    "file_size_bytes": row.get("file_size_bytes"),
                    "preview_url": self._media_url(row.get("preview_path")),
                    "video_url": (
                        self._source_video_url(
                            row.get("source_path"),
                            sample_date=str(row.get("sample_date", "")),
                            sequence=sequences.get(asset_id, 1),
                        )
                        if media_type == "video"
                        else None
                    ),
                    "representative_frames": representative_frames,
                    "frame_count": row.get("frame_count"),
                    "fps": row.get("fps"),
                    "duration_seconds": row.get("duration_seconds"),
                    "turbidity_visual_proxy": row.get("turbidity_visual_proxy"),
                    "sharpness_laplacian": row.get("sharpness_laplacian"),
                }
            )

        return {
            **summary,
            "preview_assets": preview_assets,
        }

    def _source_video_url(
        self,
        source_path: Any,
        *,
        sample_date: str = "",
        sequence: int = 1,
    ) -> str | None:
        """The playable URL for a source video, when it is actually on disk.

        Tried at its recorded ``source_path``, by basename under the persistent
        media drop, then by the canonical ``<date>_<ordinal>.<ext>`` name that
        matches the label the UI shows. The raw UAV tree is gitignored and
        overwritten by releases, so the media drop is the durable place to put a
        video; when none exists this is ``None`` and the UI shows the frames.
        """
        if not source_path:
            return None
        suffix = Path(str(source_path)).suffix or ".mp4"
        candidates = [
            str(source_path),
            str(MEDIA_UAV_ROOT / Path(str(source_path)).name),
        ]
        if sample_date:
            for variant in {suffix, suffix.lower(), ".mp4", ".mov"}:
                candidates.append(
                    str(MEDIA_UAV_ROOT / f"{sample_date}_{int(sequence):02d}{variant}")
                )
        for candidate in candidates:
            try:
                self.resolve_media_path(candidate)
            except FileNotFoundError:
                continue
            return self._media_url(candidate)
        return None

    def resolve_media_path(self, relative_path: str) -> Path:
        candidate = (self.settings.runtime_root / relative_path).resolve()
        allowed_roots = [
            (self.settings.runtime_root / root).resolve() for root in ALLOWED_MEDIA_ROOTS
        ]
        if not candidate.is_file() or not any(
            root == candidate or root in candidate.parents for root in allowed_roots
        ):
            raise FileNotFoundError(relative_path)
        return candidate
