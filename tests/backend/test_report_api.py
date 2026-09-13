from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import main as main_module
from tests.backend._helpers import admin_auth_guard
from tests.backend.test_report_builder import FakeRepository


class ReportApiTest(unittest.TestCase):
    def test_export_report_returns_selected_format_and_downloads_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir)
            test_settings = replace(main_module.settings, report_root=report_root)
            provenance = {"case_id": "case-1", "run_id": "job-1", "scope": "case"}
            with patch.object(main_module, "settings", test_settings), patch.object(
                main_module,
                "resolve_artifacts",
                return_value=(FakeRepository(), provenance),
            ):
                payload = main_module.export_report(
                    case_id="case-1", format="md", actor="tester", _=None
                )
                self.assertEqual(payload["format"], "md")
                self.assertTrue(payload["filename"].endswith(".md"))
                # The rendered file is attributable to the run it came from.
                self.assertEqual(payload["provenance"], provenance)

                response = main_module.download_report(payload["filename"])
                self.assertIn("text/markdown", response.media_type)

                content = Path(response.path).read_text(encoding="utf-8")
                self.assertIn("# WaterExpert 水环境智能诊断报告", content)
                self.assertIn("外源输入", content)

    def test_export_route_accepts_integrated_scope_and_keeps_provenance(self) -> None:
        """HTTP-level guard: the export response is valid FastAPI output.

        Regression: the route was annotated ``-> dict[str, str]`` while its body
        carries a nested ``provenance`` dict, so every successful export died in
        response validation (500) before reaching the client.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_settings = replace(main_module.settings, report_root=Path(tmp_dir))
            provenance = {"scope": "integrated", "is_integrated_default": True}
            main_module.app.dependency_overrides[main_module.auth_guard] = admin_auth_guard
            main_module.app.dependency_overrides[main_module.current_actor] = lambda: "tester"
            try:
                with patch.object(main_module, "settings", test_settings), patch.object(
                    main_module,
                    "resolve_artifacts",
                    return_value=(FakeRepository(), provenance),
                ):
                    client = TestClient(main_module.app)
                    response = client.post(
                        "/api/v1/report/export",
                        params={"format": "md", "scope": "integrated"},
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    body = response.json()
                    self.assertEqual(body["format"], "md")
                    self.assertTrue(body["filename"].endswith(".md"))
                    self.assertEqual(body["provenance"], provenance)
            finally:
                main_module.app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
