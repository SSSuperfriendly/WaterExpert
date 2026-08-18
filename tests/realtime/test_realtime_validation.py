from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from backend.app.config import get_settings
from backend.app.services.realtime_validation import RealtimeValidationService


class RealtimeValidationServiceTest(unittest.TestCase):
    def _service(self, tmp_root: Path) -> RealtimeValidationService:
        settings = replace(get_settings(), project_root=tmp_root)
        return RealtimeValidationService(settings)

    def test_latest_returns_missing_when_artifact_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(Path(tmp_dir))
            self.assertEqual(service.latest()["status"], "missing")

    def test_latest_returns_payload_when_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(Path(tmp_dir))
            service.artifact_path.parent.mkdir(parents=True, exist_ok=True)
            service.artifact_path.write_text(
                json.dumps({"status": "ok", "target_section": "吴淞口"}, ensure_ascii=False),
                encoding="utf-8",
            )
            payload = service.latest()
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["target_section"], "吴淞口")

    def test_latest_returns_error_when_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(Path(tmp_dir))
            service.artifact_path.parent.mkdir(parents=True, exist_ok=True)
            service.artifact_path.write_text("{not json", encoding="utf-8")
            self.assertEqual(service.latest()["status"], "error")

    def test_latest_returns_error_when_not_a_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(Path(tmp_dir))
            service.artifact_path.parent.mkdir(parents=True, exist_ok=True)
            service.artifact_path.write_text("[1, 2]", encoding="utf-8")
            self.assertEqual(service.latest()["status"], "error")


if __name__ == "__main__":
    unittest.main()
