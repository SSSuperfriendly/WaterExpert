from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from backend.app.services.report_builder import get_report_media_type, write_report


class FakeRepository:
    def dashboard(self) -> dict:
        return {
            "station_profile": {
                "station_name": "吴淞口",
                "river": "黄浦江",
                "matched_model_rows": 92,
            },
            "prototype_scope": "单站点日尺度原型",
            "guardrails": ["仅用于结果研判。"],
            "test_models": {
                "cmfbe_stgcn": {
                    "turbidity_r2": 0.82,
                    "turbidity_rmse": 1.23,
                    "clearness_r2": 0.77,
                    "clearness_rmse": 0.31,
                }
            },
            "high_priority_days": [
                {
                    "target_date": "2024-01-01",
                    "primary_scenario": "external_input",
                    "risk_band": "high",
                    "predicted_critical_transition_prob": 0.93,
                    "evidence_summary": "降雨增强; 径流抬升",
                }
            ],
        }

    def predictions(self, model=None, split="test") -> dict:
        return {
            "selected_model": "cmfbe_stgcn",
            "series": [
                {
                    "target_date": "2024-01-01",
                    "actual_turbidity": 11.2,
                    "predicted_turbidity": 10.9,
                    "actual_clearness": 3.5,
                    "predicted_clearness": 3.4,
                    "predicted_critical_transition_prob": 0.93,
                }
            ],
        }

    def diagnostics(self) -> dict:
        return {
            "factor_summary": {
                "top_driver_features": [
                    {
                        "feature": "runoff_source",
                        "feature_label": "径流输入",
                        "driver_score": 0.81,
                    }
                ]
            },
            "process_decomposition": [
                {
                    "process_label": "径流来源",
                    "direction": "source",
                    "mean_contribution": 1.2,
                    "std_contribution": 0.3,
                    "max_contribution": 1.8,
                }
            ],
        }

    def scenario_triage(self) -> dict:
        return {
            "classification_semantics": "经验分诊标签。",
        }

    def thresholds(self, feature=None) -> dict:
        return {
            "threshold_semantics": "经验阈值。",
            "summary": [
                {
                    "feature_label": "3日累计降雨",
                    "threshold": 21.5,
                    "unit": "mm",
                    "r2_gain": 0.11,
                    "response_jump": 0.32,
                    "status": "watch",
                }
            ],
        }

    def boundary(self) -> dict:
        return {
            "summary": {
                "models": {
                    "cmfbe_stgcn": {"test": {"f1": 0.7, "accuracy": 0.8}},
                    "mscim": {"test": {"f1": 0.6, "accuracy": 0.74}},
                },
                "overall": {
                    "test": {
                        "positive_rate": 0.27,
                        "labeled_samples": 41,
                    }
                },
            }
        }

    def sensitivity(self) -> dict:
        return {
            "sobol": {
                "top_factors": [
                    {
                        "factor_label": "径流泥沙脉冲",
                        "first_order_index": 0.28,
                        "total_order_index": 0.39,
                        "interaction_strength": 0.11,
                    }
                ]
            }
        }


class ReportBuilderTest(unittest.TestCase):
    def test_write_report_supports_multiple_formats(self) -> None:
        repository = FakeRepository()
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir)
            for export_format, marker in {
                "html": "WaterExpert 水环境智能诊断报告",
                "md": "# WaterExpert 水环境智能诊断报告",
                "json": '"selected_model": "cmfbe_stgcn"',
                "pdf": "%PDF",
            }.items():
                path = write_report(repository, report_root, export_format=export_format)
                self.assertTrue(path.exists())
                self.assertEqual(path.suffix, {"html": ".html", "md": ".md", "json": ".json", "pdf": ".pdf"}[export_format])
                if export_format == "pdf":
                    content = path.read_bytes()
                    self.assertTrue(content.startswith(marker.encode("utf-8")))
                else:
                    content = path.read_text(encoding="utf-8")
                    self.assertIn(marker, content)

    def test_markdown_report_localizes_core_labels_to_chinese(self) -> None:
        repository = FakeRepository()
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = write_report(repository, Path(tmp_dir), export_format="md")
            content = path.read_text(encoding="utf-8")
            self.assertIn("单站点日尺度原型", content)
            self.assertIn("外源输入", content)
            self.assertIn("高", content)
            self.assertIn("边界说明", content)
            self.assertIn("当前主模型：cmfbe_stgcn", content)
            self.assertNotIn("external_input", content)
            self.assertNotIn("single-station multimodal daily prototype", content)

    def test_html_report_localizes_thresholds_and_guardrails(self) -> None:
        repository = FakeRepository()
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = write_report(repository, Path(tmp_dir), export_format="html")
            content = path.read_text(encoding="utf-8")
            self.assertIn("经验阈值。", content)
            self.assertIn("仅用于结果研判。", content)
            self.assertIn("3日累计降雨", content)
            self.assertIn("关注", content)

    def test_pdf_report_extracts_chinese_body_text(self) -> None:
        repository = FakeRepository()
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = write_report(repository, Path(tmp_dir), export_format="pdf")
            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("WaterExpert 水环境智能诊断报告", text)
            self.assertIn("吴淞口", text)
            self.assertIn("边界说明", text)
            self.assertIn("当前主模型：cmfbe_stgcn", text)
            self.assertIn("外源输入", text)
            self.assertIn("经验阈值。", text)

    def test_report_media_type_matches_file_suffix(self) -> None:
        self.assertEqual(
            get_report_media_type(Path("report.html")),
            "text/html; charset=utf-8",
        )
        self.assertEqual(
            get_report_media_type(Path("report.md")),
            "text/markdown; charset=utf-8",
        )
        self.assertEqual(
            get_report_media_type(Path("report.json")),
            "application/json",
        )
        self.assertEqual(
            get_report_media_type(Path("report.pdf")),
            "application/pdf",
        )

    def test_json_report_is_valid_json(self) -> None:
        repository = FakeRepository()
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = write_report(repository, Path(tmp_dir), export_format="json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["selected_model"], "cmfbe_stgcn")
            self.assertEqual(payload["dashboard"]["station_profile"]["station_name"], "吴淞口")

    def test_write_report_uses_unique_filenames_for_back_to_back_exports(self) -> None:
        repository = FakeRepository()
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir)
            first = write_report(repository, report_root, export_format="html")
            second = write_report(repository, report_root, export_format="html")
            self.assertNotEqual(first.name, second.name)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())


if __name__ == "__main__":
    unittest.main()

