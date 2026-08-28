from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from backend.app.config import get_settings
from backend.app.domain.codes import DatasetStatus, ErrorCode, IngestionStage
from backend.app.services.dataset_service import DatasetNotFound, DatasetService
from backend.app.services.state_store import SqliteStateStore
from backend.app.services.upload_guard import UploadRejected


def _water_quality_csv(days: int = 60, turbidity: float | None = None) -> bytes:
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    frame = pd.DataFrame(
        {
            "监测时间": [day.date().isoformat() for day in dates],
            "站点": ["2586"] * days,
            "浊度": [turbidity if turbidity is not None else 30.0 + i for i in range(days)],
            "水温": [15.0] * days,
            "pH": [7.4] * days,
        }
    )
    return frame.to_csv(index=False).encode("utf-8-sig")


class DatasetServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        base = get_settings()
        self.settings = replace(
            base,
            project_root=root,
            runtime_root=root,
            state_root=root / "state",
            report_root=root / "reports",
        )
        self.store = SqliteStateStore(self.settings.state_root)
        self.service = DatasetService(self.settings, self.store)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _upload(self, payload: bytes, filename: str = "wq.csv", **kwargs) -> dict:
        return self.service.ingest_upload(
            source=io.BytesIO(payload),
            filename=filename,
            data_type=kwargs.pop("data_type", "water_quality"),
            station_code=kwargs.pop("station_code", "2586"),
            owner=kwargs.pop("owner", "tester"),
            **kwargs,
        )


class IngestUploadTest(DatasetServiceTestCase):
    def test_accepted_upload_creates_dataset_and_version(self) -> None:
        version = self._upload(_water_quality_csv())

        self.assertEqual(version["status"], str(DatasetStatus.ACCEPTED))
        self.assertEqual(version["stage"], str(IngestionStage.ACCEPTED))
        self.assertEqual(version["modelable"], "1")
        self.assertEqual(version["version"], "1")
        self.assertEqual(version["station_coverage"], ["2586"])

        dataset = self.service.get_dataset(version["dataset_id"])
        self.assertEqual(dataset["status"], str(DatasetStatus.ACCEPTED))
        self.assertEqual(dataset["version_count"], 1)
        self.assertEqual(dataset["latest_accepted_version_id"], version["version_id"])

    def test_second_upload_to_same_dataset_becomes_version_two(self) -> None:
        first = self._upload(_water_quality_csv())
        second = self._upload(_water_quality_csv(), dataset_id=first["dataset_id"])

        self.assertEqual(second["version"], "2")
        self.assertEqual(len(self.service.list_versions(first["dataset_id"])), 2)
        self.assertEqual(self.service.get_dataset(first["dataset_id"])["version_count"], 2)

    def test_rejected_upload_is_recorded_with_the_blocking_stage(self) -> None:
        """A file missing turbidity is stored and explained, not silently dropped."""
        frame = pd.DataFrame({"监测时间": ["2024-01-01"], "站点": ["2586"], "水温": [15.0]})
        version = self._upload(frame.to_csv(index=False).encode("utf-8-sig"))

        self.assertEqual(version["status"], str(DatasetStatus.REJECTED))
        self.assertEqual(version["blocked_at"], str(IngestionStage.VALIDATED))
        self.assertEqual(version["modelable"], "0")
        self.assertIn("missing_required_fields", version["blocking_reasons"])

    def test_upload_rejects_unsupported_extension_before_writing(self) -> None:
        with self.assertRaises(UploadRejected) as ctx:
            self._upload(b"whatever", filename="payload.exe")
        self.assertEqual(ctx.exception.code, ErrorCode.UNSUPPORTED_FORMAT)

    def test_upload_rejects_binary_content_disguised_as_csv(self) -> None:
        with self.assertRaises(UploadRejected) as ctx:
            self._upload(b"\x00\x01\x02binary", filename="fake.csv")
        self.assertEqual(ctx.exception.code, ErrorCode.CONTENT_TYPE_REJECTED)

    def test_upload_enforces_the_size_cap(self) -> None:
        self.service.settings = replace(self.settings, max_upload_bytes=64)
        with self.assertRaises(UploadRejected) as ctx:
            self._upload(_water_quality_csv())
        self.assertEqual(ctx.exception.code, ErrorCode.FILE_TOO_LARGE)

    def test_unsupported_data_type_is_rejected(self) -> None:
        with self.assertRaises(UploadRejected) as ctx:
            self._upload(_water_quality_csv(), data_type="astrology")
        self.assertEqual(ctx.exception.code, ErrorCode.VALIDATION_FAILED)

    def test_upload_into_dataset_of_a_different_type_is_rejected(self) -> None:
        first = self._upload(_water_quality_csv())
        with self.assertRaises(UploadRejected):
            self._upload(
                _water_quality_csv(),
                data_type="weather",
                dataset_id=first["dataset_id"],
            )


class ManagedPathImportTest(DatasetServiceTestCase):
    def test_imports_from_the_managed_inbox(self) -> None:
        inbox = self.settings.managed_import_root
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "wq.csv").write_bytes(_water_quality_csv())

        version = self.service.ingest_managed_path(
            relative_path="wq.csv",
            data_type="water_quality",
            station_code="2586",
            owner="tester",
        )

        self.assertEqual(version["status"], str(DatasetStatus.ACCEPTED))
        self.assertEqual(version["source_kind"], "managed_path")

    def test_refuses_paths_outside_the_managed_inbox(self) -> None:
        outside = Path(self._tmp.name) / "secret.csv"
        outside.write_bytes(_water_quality_csv())

        for candidate in (str(outside), "../secret.csv", "/etc/passwd"):
            with self.subTest(path=candidate):
                with self.assertRaises(UploadRejected) as ctx:
                    self.service.ingest_managed_path(
                        relative_path=candidate,
                        data_type="water_quality",
                        station_code="2586",
                        owner="tester",
                    )
                self.assertEqual(ctx.exception.code, ErrorCode.PATH_NOT_ALLOWED)


class ModellingGateTest(DatasetServiceTestCase):
    def test_assert_modelable_passes_for_accepted_versions(self) -> None:
        version = self._upload(_water_quality_csv())
        self.assertEqual(
            self.service.assert_modelable(version["version_id"])["version_id"],
            version["version_id"],
        )

    def test_assert_modelable_blocks_rejected_versions(self) -> None:
        frame = pd.DataFrame({"监测时间": ["2024-01-01"], "站点": ["2586"], "水温": [15.0]})
        version = self._upload(frame.to_csv(index=False).encode("utf-8-sig"))

        with self.assertRaises(UploadRejected) as ctx:
            self.service.assert_modelable(version["version_id"])
        self.assertEqual(ctx.exception.code, ErrorCode.DATASET_NOT_MODELABLE)

    def test_modelable_versions_filters_by_type_and_station(self) -> None:
        self._upload(_water_quality_csv())

        self.assertEqual(len(self.service.modelable_versions(data_type="water_quality")), 1)
        self.assertEqual(len(self.service.modelable_versions(data_type="weather")), 0)
        self.assertEqual(len(self.service.modelable_versions(station_code="2586")), 1)
        self.assertEqual(len(self.service.modelable_versions(station_code="9999")), 0)

    def test_coverage_window_intersects_versions(self) -> None:
        first = self._upload(_water_quality_csv(days=60))
        start, end = self.service.coverage_window([first["version_id"]])
        self.assertEqual(start, "2024-01-01")
        self.assertEqual(end, "2024-02-29")


class LineageAndLifecycleTest(DatasetServiceTestCase):
    def test_case_usage_is_recorded_in_lineage(self) -> None:
        version = self._upload(_water_quality_csv())
        self.service.record_case_usage([version["version_id"]], "case-1")

        lineage = self.service.lineage(version["version_id"])
        self.assertEqual(lineage["used_by_cases"], ["case-1"])

    def test_delete_is_refused_while_a_case_uses_the_data(self) -> None:
        version = self._upload(_water_quality_csv())
        self.service.record_case_usage([version["version_id"]], "case-1")

        with self.assertRaises(UploadRejected) as ctx:
            self.service.delete_dataset(version["dataset_id"], actor="tester")
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_STATE_TRANSITION)

    def test_delete_removes_records_and_files(self) -> None:
        version = self._upload(_water_quality_csv())
        dataset_id = version["dataset_id"]
        root = self.settings.datasets_root / dataset_id
        self.assertTrue(root.exists())

        result = self.service.delete_dataset(dataset_id, actor="tester")

        self.assertEqual(result["deleted_versions"], 1)
        self.assertFalse(root.exists())
        with self.assertRaises(DatasetNotFound):
            self.service.get_dataset(dataset_id)

    def test_archive_keeps_the_record_but_marks_it_archived(self) -> None:
        version = self._upload(_water_quality_csv())
        archived = self.service.archive_dataset(version["dataset_id"], actor="tester")
        self.assertEqual(archived["status"], str(DatasetStatus.ARCHIVED))

    def test_purge_expired_removes_only_old_rejected_versions(self) -> None:
        frame = pd.DataFrame({"监测时间": ["2024-01-01"], "站点": ["2586"], "水温": [15.0]})
        rejected = self._upload(frame.to_csv(index=False).encode("utf-8-sig"))
        accepted = self._upload(_water_quality_csv())

        fresh = self.service.purge_expired()
        self.assertEqual(fresh["purged"], 0)

        future = datetime.now(timezone.utc) + timedelta(
            days=self.settings.upload_retention_days + 1
        )
        aged = self.service.purge_expired(now=future)

        self.assertEqual(aged["purged"], 1)
        with self.assertRaises(DatasetNotFound):
            self.service.get_version(rejected["version_id"])
        self.assertEqual(
            self.service.get_version(accepted["version_id"])["version_id"],
            accepted["version_id"],
        )


class ReportingSurfaceTest(DatasetServiceTestCase):
    def test_preview_returns_canonical_columns(self) -> None:
        version = self._upload(_water_quality_csv())
        preview = self.service.preview(version["version_id"], limit=5)

        self.assertTrue(preview["available"])
        self.assertIn("turbidity", preview["columns"])
        self.assertEqual(len(preview["rows"]), 5)

    def test_preview_of_a_rejected_version_explains_itself(self) -> None:
        frame = pd.DataFrame({"监测时间": ["2024-01-01"], "站点": ["2586"], "水温": [15.0]})
        version = self._upload(frame.to_csv(index=False).encode("utf-8-sig"))

        preview = self.service.preview(version["version_id"])
        self.assertFalse(preview["available"])
        self.assertEqual(preview["reason"], str(IngestionStage.VALIDATED))

    def test_quality_report_round_trips_the_stage_chain(self) -> None:
        version = self._upload(_water_quality_csv())
        report = self.service.quality_report(version["version_id"])

        self.assertEqual(report["final_stage"], str(IngestionStage.ACCEPTED))
        stages = [item["stage"] for item in report["stages"]]
        self.assertEqual(stages[0], str(IngestionStage.UPLOADED))
        self.assertIn(str(IngestionStage.ALIGNED), stages)

    def test_freshness_summary_counts_and_flags_staleness(self) -> None:
        self._upload(_water_quality_csv())
        summary = self.service.freshness_summary()

        self.assertEqual(summary["dataset_count"], 1)
        self.assertEqual(summary["modelable_count"], 1)
        self.assertEqual(summary["latest_coverage_end"], "2024-02-29")
        self.assertTrue(summary["is_stale"])  # the fixture data is from 2024

    def test_quality_alerts_list_rejected_versions(self) -> None:
        frame = pd.DataFrame({"监测时间": ["2024-01-01"], "站点": ["2586"], "水温": [15.0]})
        self._upload(frame.to_csv(index=False).encode("utf-8-sig"))

        alerts = self.service.quality_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertIn("missing_required_fields", alerts[0]["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
