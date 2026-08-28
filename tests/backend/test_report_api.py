from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from backend.app import main as main_module

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


if __name__ == "__main__":
    unittest.main()
