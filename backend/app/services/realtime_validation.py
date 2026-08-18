from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.config import Settings
from backend.app.services.artifact_io import ArtifactReadError, read_json


class RealtimeValidationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.artifact_path = settings.var_root / "realtime" / "latest_validation.json"

    def latest(self) -> dict[str, Any]:
        if not self.artifact_path.exists():
            return {
                "status": "missing",
                "message": "Latest realtime validation artifact not found. Run scripts/realtime/validate_latest_realtime.py first.",
            }
        try:
            return read_json(self.artifact_path)
        except ArtifactReadError as exc:
            return {
                "status": "error",
                "message": f"Failed to read latest realtime validation artifact: {exc}",
            }
