from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd

from backend.app.config import get_settings
from backend.app.services.artifact_repository import ArtifactRepository


class ArtifactRepositoryTest(unittest.TestCase):
    def test_dashboard_falls_back_to_agent_best_model_summary(self) -> None:
        base_settings = get_settings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            runtime_root = tmp_root / "runtime"
            outputs_root = runtime_root / "outputs"
            settings = replace(
                base_settings,
                runtime_root=runtime_root,
                state_root=tmp_root / "state",
                report_root=tmp_root / "reports",
            )
            (runtime_root / "src" / "water_ai").mkdir(parents=True, exist_ok=True)
            (runtime_root / "src" / "water_ai" / "__init__.py").write_text("", encoding="utf-8")
            (outputs_root / "agent").mkdir(parents=True, exist_ok=True)
            (outputs_root / "metrics").mkdir(parents=True, exist_ok=True)
            (outputs_root / "predictions").mkdir(parents=True, exist_ok=True)
            settings.default_config_path.parent.mkdir(parents=True, exist_ok=True)
            settings.default_config_path.write_text("output_dir: outputs\n", encoding="utf-8")

            (outputs_root / "agent" / "agent_context.json").write_text(
                json.dumps(
                    {
                        "best_model_summary": {
                            "best_test_turbidity_model": "cmfbe_stgcn",
                            "best_test_clearness_model": "mscim",
                        },
                        "test_models": {},
                        "guardrails": [],
                    }
                ),
                encoding="utf-8",
            )
            (outputs_root / "metrics" / "metrics.json").write_text(
                json.dumps(
                    {
                        "data": {
                            "dataset_summary": {
                                "water_station": {},
                                "notes": {"current_scope": "prototype"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                [{"model": "cmfbe_stgcn", "split": "test", "target_date": "2024-01-01"}]
            ).to_csv(outputs_root / "predictions" / "predictions.csv", index=False)

            repository = ArtifactRepository(settings)
            dashboard = repository.dashboard()
            self.assertEqual(
                dashboard["best_model_summary"]["best_test_turbidity_model"],
                "cmfbe_stgcn",
            )

    def test_diagnostics_falls_back_to_prediction_derived_process_summary(self) -> None:
        base_settings = get_settings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            runtime_root = tmp_root / "runtime"
            outputs_root = runtime_root / "outputs"
            settings = replace(
                base_settings,
                runtime_root=runtime_root,
                state_root=tmp_root / "state",
                report_root=tmp_root / "reports",
            )
            (runtime_root / "src" / "water_ai").mkdir(parents=True, exist_ok=True)
            (runtime_root / "src" / "water_ai" / "__init__.py").write_text("", encoding="utf-8")
            (outputs_root / "predictions").mkdir(parents=True, exist_ok=True)
            (outputs_root / "diagnosis").mkdir(parents=True, exist_ok=True)
            (outputs_root / "agent").mkdir(parents=True, exist_ok=True)
            (outputs_root / "metrics").mkdir(parents=True, exist_ok=True)
            settings.default_config_path.parent.mkdir(parents=True, exist_ok=True)
            settings.default_config_path.write_text("output_dir: outputs\n", encoding="utf-8")

            pd.DataFrame(
                [
                    {
                        "model": "cmfbe_stgcn",
                        "split": "test",
                        "target_date": "2024-01-01",
                        "runoff_source": 1.2,
                        "erosion_source": 0.3,
                        "tidal_source": 0.4,
                        "phytoplankton_source": 0.1,
                        "krone_deposition_sink": 0.2,
                        "flushing_sink": 0.5,
                        "purification_sink": 0.15,
                    }
                ]
            ).to_csv(outputs_root / "predictions" / "predictions.csv", index=False)
            (outputs_root / "diagnosis" / "mscim_turbidity_factor_diagnosis_summary.json").write_text(
                json.dumps({"top_driver_features": []}),
                encoding="utf-8",
            )
            pd.DataFrame([{"domain": "hydrodynamics", "score": 1.0}]).to_csv(
                outputs_root / "diagnosis" / "mscim_turbidity_domain_diagnosis.csv",
                index=False,
            )
            (outputs_root / "agent" / "agent_context.json").write_text(
                json.dumps({"best_model_summary": {"best_test_turbidity_model": "cmfbe_stgcn"}, "test_models": {}, "guardrails": []}),
                encoding="utf-8",
            )
            (outputs_root / "metrics" / "metrics.json").write_text(
                json.dumps({"data": {"dataset_summary": {"water_station": {}, "notes": {"current_scope": "prototype"}}}}),
                encoding="utf-8",
            )

            repository = ArtifactRepository(settings)
            diagnostics = repository.diagnostics()
            self.assertGreater(len(diagnostics["process_decomposition"]), 0)
            self.assertEqual(diagnostics["process_decomposition"][0]["process_key"], "runoff_source")

    def test_boundary_returns_fallback_label_summary_when_artifact_missing(self) -> None:
        base_settings = get_settings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            runtime_root = tmp_root / "runtime"
            outputs_root = runtime_root / "outputs"
            settings = replace(
                base_settings,
                runtime_root=runtime_root,
                state_root=tmp_root / "state",
                report_root=tmp_root / "reports",
            )
            (runtime_root / "src" / "water_ai").mkdir(parents=True, exist_ok=True)
            (runtime_root / "src" / "water_ai" / "__init__.py").write_text("", encoding="utf-8")
            (outputs_root / "boundary").mkdir(parents=True, exist_ok=True)
            (outputs_root / "boundary" / "boundary_detection_summary.json").write_text(
                json.dumps({"status": "evaluated", "overall": {"test": {"labeled_samples": 7}}}),
                encoding="utf-8",
            )
            pd.DataFrame([{"split": "test", "target_date": "2024-01-01", "predicted_boundary_probability": 0.9}]).to_csv(
                outputs_root / "boundary" / "boundary_predictions.csv",
                index=False,
            )

            repository = ArtifactRepository(settings)
            boundary = repository.boundary()
            self.assertEqual(boundary["label_generation_summary"]["status"], "evaluated")
            self.assertEqual(boundary["label_generation_summary"]["labeled_days"], 7)

    def test_predictions_tolerate_invalid_target_dates(self) -> None:
        base_settings = get_settings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            runtime_root = tmp_root / "runtime"
            outputs_root = runtime_root / "outputs"
            settings = replace(
                base_settings,
                runtime_root=runtime_root,
                state_root=tmp_root / "state",
                report_root=tmp_root / "reports",
            )
            (runtime_root / "src" / "water_ai").mkdir(parents=True, exist_ok=True)
            (runtime_root / "src" / "water_ai" / "__init__.py").write_text("", encoding="utf-8")
            (outputs_root / "predictions").mkdir(parents=True, exist_ok=True)
            (outputs_root / "agent").mkdir(parents=True, exist_ok=True)
            (outputs_root / "metrics").mkdir(parents=True, exist_ok=True)
            settings.default_config_path.parent.mkdir(parents=True, exist_ok=True)
            settings.default_config_path.write_text("output_dir: outputs\n", encoding="utf-8")

            pd.DataFrame(
                [
                    {
                        "model": "cmfbe_stgcn",
                        "split": "test",
                        "target_date": "not-a-date",
                        "actual_turbidity": 1.2,
                        "predicted_turbidity": 1.3,
                    }
                ]
            ).to_csv(outputs_root / "predictions" / "predictions.csv", index=False)
            pd.DataFrame([{"model": "cmfbe_stgcn", "turbidity_r2": 0.82}]).to_csv(
                outputs_root / "metrics" / "model_comparison.csv",
                index=False,
            )
            (outputs_root / "agent" / "agent_context.json").write_text(
                json.dumps(
                    {
                        "best_model_summary": {"best_test_turbidity_model": "cmfbe_stgcn"},
                        "test_models": {"cmfbe_stgcn": {"turbidity_r2": 0.82}},
                        "guardrails": [],
                    }
                ),
                encoding="utf-8",
            )
            (outputs_root / "metrics" / "metrics.json").write_text(
                json.dumps({"data": {"dataset_summary": {"water_station": {}, "notes": {"current_scope": "prototype"}}}}),
                encoding="utf-8",
            )

            repository = ArtifactRepository(settings)
            predictions = repository.predictions(model="cmfbe_stgcn", split="test")
            self.assertEqual(len(predictions["series"]), 1)
            self.assertIsNone(predictions["series"][0]["target_date"])


if __name__ == "__main__":
    unittest.main()
