from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from backend.app.config import Settings


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
            payload = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
            return {
                "status": "error",
                "message": f"Failed to read latest realtime validation artifact: {exc}",
            }
        if not isinstance(payload, dict):
            return {
                "status": "error",
                "message": "Latest realtime validation artifact is not a JSON object.",
            }
        return payload
