"""A submitted job's parameters must reach the pipeline or be refused.

Review item 1: the UI collected a model, a station and a date range; the job
record stored them; and the pipeline never saw any of it. These tests cover the
two halves of the fix — the config snapshot the runner actually hands to the
pipeline, and the submit-time checks that refuse an impossible request.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import yaml

from backend.app.config import get_settings
from backend.app.domain.codes import ErrorCode
from backend.app.domain.models import REQUIRED_MODEL_KEYS
from backend.app.schemas import PredictionJobCreateRequest
from backend.app.services.artifact_repository import ArtifactRepository
from backend.app.services.runtime_jobs import JobParameterError, RuntimeJobService
from backend.app.services.state_store import SqliteStateStore


class JobParameterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.settings = replace(
            get_settings(),
            state_root=root / "state",
            report_root=root / "reports",
        )
        self.service = RuntimeJobService(
            self.settings,
            ArtifactRepository(self.settings),
            SqliteStateStore(self.settings.state_root),
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _snapshot(self, **kwargs) -> dict:
        """Materialize a job config the way create_prediction_job does."""
        payload = PredictionJobCreateRequest(**kwargs)
        run_root = Path(self._tmp.name) / "run"
        run_root.mkdir(parents=True, exist_ok=True)
        path = self.service._materialize_job_config(
            run_root=run_root,
            output_root=run_root / "outputs",
            config_path=self.settings.default_config_path,
            payload=payload,
        )
        return yaml.safe_load(path.read_text(encoding="utf-8"))


class ConfigSnapshotTest(JobParameterTestCase):
    def test_the_requested_dates_reach_the_pipeline_config(self) -> None:
        snapshot = self._snapshot(start_date="2024-03-01", end_date="2024-06-30")

        self.assertEqual(snapshot["run_scope"]["start_date"], "2024-03-01")
        self.assertEqual(snapshot["run_scope"]["end_date"], "2024-06-30")

    def test_the_requested_station_reaches_the_pipeline_config(self) -> None:
        snapshot = self._snapshot(station_code="2586")
        self.assertEqual(snapshot["run_scope"]["station_code"], "2586")

    def test_absent_dates_become_null_rather_than_empty_strings(self) -> None:
        """The pipeline treats null as 'all available data'; '' would be a parse error."""
        snapshot = self._snapshot()
        self.assertIsNone(snapshot["run_scope"]["start_date"])
        self.assertIsNone(snapshot["run_scope"]["end_date"])

    def test_the_requested_model_leads_the_enabled_list(self) -> None:
        snapshot = self._snapshot(model_name="mscim")
        self.assertEqual(snapshot["models"]["enabled"][0], "mscim")

    def test_required_models_are_added_to_the_selection(self) -> None:
        snapshot = self._snapshot(model_name="mscim")
        for key in REQUIRED_MODEL_KEYS:
            self.assertIn(key, snapshot["models"]["enabled"])

    def test_a_run_scope_is_not_written_without_a_payload(self) -> None:
        """The snapshot for a job with no request keeps the config's own scope."""
        run_root = Path(self._tmp.name) / "plain"
        run_root.mkdir(parents=True, exist_ok=True)
        path = self.service._materialize_job_config(
            run_root=run_root,
            output_root=run_root / "outputs",
            config_path=self.settings.default_config_path,
        )
        snapshot = yaml.safe_load(path.read_text(encoding="utf-8"))
        default = yaml.safe_load(
            self.settings.default_config_path.read_text(encoding="utf-8")
        )
        self.assertEqual(snapshot["run_scope"], default["run_scope"])

    def test_output_redirection_still_applies(self) -> None:
        snapshot = self._snapshot()
        self.assertTrue(snapshot["output_dir"].endswith("outputs"))


class SubmitValidationTest(JobParameterTestCase):
    def _validate(self, coverage=None, **kwargs) -> None:
        self.service.validate_job_parameters(
            PredictionJobCreateRequest(**kwargs), coverage=coverage
        )

    def test_a_request_inside_the_coverage_window_is_accepted(self) -> None:
        self._validate(
            start_date="2024-02-01",
            end_date="2024-05-01",
            coverage=("2024-01-01", "2024-12-31"),
        )

    def test_a_start_date_before_the_data_is_refused(self) -> None:
        with self.assertRaises(JobParameterError) as ctx:
            self._validate(start_date="2019-01-01", coverage=("2024-01-01", "2024-12-31"))
        self.assertEqual(ctx.exception.code, ErrorCode.DATE_RANGE_OUT_OF_COVERAGE)
        self.assertIn("2024-01-01", ctx.exception.detail)

    def test_an_end_date_after_the_data_is_refused(self) -> None:
        with self.assertRaises(JobParameterError) as ctx:
            self._validate(end_date="2030-01-01", coverage=("2024-01-01", "2024-12-31"))
        self.assertEqual(ctx.exception.code, ErrorCode.DATE_RANGE_OUT_OF_COVERAGE)

    def test_an_inverted_range_is_refused(self) -> None:
        with self.assertRaises(JobParameterError) as ctx:
            self._validate(start_date="2024-06-01", end_date="2024-01-01")
        self.assertEqual(ctx.exception.code, ErrorCode.VALIDATION_FAILED)

    def test_a_malformed_date_is_refused(self) -> None:
        with self.assertRaises(JobParameterError) as ctx:
            self._validate(start_date="not-a-date")
        self.assertEqual(ctx.exception.code, ErrorCode.VALIDATION_FAILED)

    def test_dates_are_not_checked_against_coverage_when_none_is_known(self) -> None:
        """Coverage is optional so a job can still run before datasets are registered."""
        self._validate(start_date="1990-01-01", end_date="2099-01-01")


class EffectiveParametersTest(JobParameterTestCase):
    def _record_with_scope(self, payload: dict | None) -> dict:
        artifact_root = Path(self._tmp.name) / "artifacts"
        (artifact_root / "metrics").mkdir(parents=True, exist_ok=True)
        if payload is not None:
            (artifact_root / "metrics" / "run_scope.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
        return {"artifact_root": str(artifact_root)}

    def test_the_applied_scope_is_read_back_from_the_pipeline(self) -> None:
        record = self._record_with_scope(
            {
                "requested_start_date": "2020-01-01",
                "effective_start_date": "2020-11-02",
                "rows_after_scope": 1200,
            }
        )
        effective = self.service._effective_parameters(record)

        self.assertEqual(effective["effective_start_date"], "2020-11-02")
        self.assertNotEqual(
            effective["effective_start_date"], effective["requested_start_date"]
        )

    def test_a_missing_scope_file_yields_no_effective_parameters(self) -> None:
        self.assertIsNone(self.service._effective_parameters(self._record_with_scope(None)))

    def test_a_corrupt_scope_file_is_ignored_rather_than_raising(self) -> None:
        record = self._record_with_scope(None)
        (Path(record["artifact_root"]) / "metrics" / "run_scope.json").write_text(
            "{not json", encoding="utf-8"
        )
        self.assertIsNone(self.service._effective_parameters(record))

    def test_a_record_without_an_artifact_root_yields_nothing(self) -> None:
        self.assertIsNone(self.service._effective_parameters({}))


class JobRecordTest(JobParameterTestCase):
    def test_the_record_carries_the_requested_parameters(self) -> None:
        record = self.service.create_prediction_job(
            PredictionJobCreateRequest(
                model_name="mscim",
                station_code="2586",
                start_date="2024-01-01",
                use_existing_artifacts=True,
            )
        )
        requested = record["requested_parameters"]

        self.assertEqual(requested["model_name"], "mscim")
        self.assertEqual(requested["start_date"], "2024-01-01")
        self.assertIn("cmfbe_stgcn", requested["models"])

    def test_the_mode_field_is_gone(self) -> None:
        """`inference` and `full_pipeline` ran the same pipeline; the choice was fake."""
        record = self.service.create_prediction_job(
            PredictionJobCreateRequest(use_existing_artifacts=True)
        )
        self.assertNotIn("mode", record)


if __name__ == "__main__":
    unittest.main()
