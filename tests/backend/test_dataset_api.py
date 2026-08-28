"""End-to-end checks on the data asset centre HTTP surface.

Review item 24: the suite had no test that actually exercised a route. These
drive the real FastAPI app with a TestClient so the wiring — status codes,
error-code bodies, the auth gate — is verified rather than assumed.

The app builds its services at import time against the real ``var/`` directory,
so each test swaps in a temp-rooted :class:`DatasetService`; nothing here
touches the developer's runtime state.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.domain.codes import ErrorCode
from backend.app.services.dataset_service import DatasetService
from backend.app.services.state_store import SqliteStateStore

from tests.backend._helpers import admin_auth_guard


def _water_quality_csv(days: int = 60) -> bytes:
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    frame = pd.DataFrame(
        {
            "监测时间": [day.date().isoformat() for day in dates],
            "站点": ["2586"] * days,
            "浊度": [30.0 + index for index in range(days)],
            "水温": [15.0] * days,
            "pH": [7.4] * days,
        }
    )
    return frame.to_csv(index=False).encode("utf-8-sig")


class DatasetApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        settings = replace(
            main.settings,
            project_root=root,
            runtime_root=root,
            state_root=root / "state",
            report_root=root / "reports",
        )
        self._original_service = main.dataset_service
        main.dataset_service = DatasetService(settings, SqliteStateStore(settings.state_root))
        self.settings = settings

        # The global auth guard is exercised by its own test below; the rest of
        # these tests are about the dataset routes, so it is stubbed out here.
        main.app.dependency_overrides[main.auth_guard] = admin_auth_guard
        main.app.dependency_overrides[main.current_actor] = lambda: "tester"
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()
        main.dataset_service = self._original_service
        self._tmp.cleanup()

    def _upload(self, payload: bytes = None, filename: str = "wq.csv", **form):
        return self.client.post(
            "/api/v1/datasets",
            data={
                "data_type": form.pop("data_type", "water_quality"),
                "station_code": form.pop("station_code", "2586"),
                **form,
            },
            files={"file": (filename, io.BytesIO(payload or _water_quality_csv()), "text/csv")},
        )


class UploadRouteTest(DatasetApiTestCase):
    def test_a_good_upload_returns_201_and_an_accepted_version(self) -> None:
        response = self._upload()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "accepted")
        self.assertEqual(body["modelable"], "1")
        self.assertEqual(body["quality_grade"], "a")

    def test_a_file_missing_turbidity_is_recorded_as_rejected_not_an_error(self) -> None:
        """A refused dataset is still a real record: it has to be explainable."""
        frame = pd.DataFrame({"监测时间": ["2024-01-01"], "站点": ["2586"], "水温": [15.0]})
        response = self._upload(frame.to_csv(index=False).encode("utf-8-sig"))

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "rejected")
        self.assertEqual(body["blocked_at"], "validated")

    def test_an_executable_is_refused_with_a_stable_code(self) -> None:
        response = self._upload(b"MZ\x90\x00", filename="payload.exe")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"], str(ErrorCode.UNSUPPORTED_FORMAT)
        )

    def test_a_binary_disguised_as_csv_is_refused(self) -> None:
        response = self._upload(b"\x00\x01\x02binary", filename="fake.csv")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"], str(ErrorCode.CONTENT_TYPE_REJECTED)
        )

    def test_an_unknown_data_type_is_refused(self) -> None:
        response = self._upload(data_type="astrology")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"], str(ErrorCode.VALIDATION_FAILED)
        )


class ManagedImportRouteTest(DatasetApiTestCase):
    def test_a_file_in_the_managed_inbox_imports(self) -> None:
        inbox = self.settings.managed_import_root
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "wq.csv").write_bytes(_water_quality_csv())

        response = self.client.post(
            "/api/v1/datasets/import",
            json={
                "data_type": "water_quality",
                "relative_path": "wq.csv",
                "station_code": "2586",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["source_kind"], "managed_path")

    def test_a_path_outside_the_inbox_is_refused_with_403(self) -> None:
        """The endpoint used to accept any path the server process could read."""
        for candidate in ("../../etc/passwd", "/etc/passwd"):
            with self.subTest(path=candidate):
                response = self.client.post(
                    "/api/v1/datasets/import",
                    json={"data_type": "water_quality", "relative_path": candidate},
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json()["detail"]["code"], str(ErrorCode.PATH_NOT_ALLOWED)
                )


class ReadRouteTest(DatasetApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.version = self._upload().json()
        self.version_id = self.version["version_id"]
        self.dataset_id = self.version["dataset_id"]

    def test_datasets_lists_the_new_dataset(self) -> None:
        body = self.client.get("/api/v1/datasets").json()
        self.assertEqual([item["dataset_id"] for item in body], [self.dataset_id])

    def test_a_dataset_can_be_fetched_by_id(self) -> None:
        response = self.client.get(f"/api/v1/datasets/{self.dataset_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version_count"], 1)

    def test_an_unknown_dataset_returns_404_with_a_code(self) -> None:
        response = self.client.get("/api/v1/datasets/nope")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], str(ErrorCode.NOT_FOUND))

    def test_the_quality_report_exposes_the_full_stage_chain(self) -> None:
        body = self.client.get(f"/api/v1/dataset-versions/{self.version_id}/quality").json()

        self.assertEqual(body["final_stage"], "accepted")
        stages = [stage["stage"] for stage in body["stages"]]
        self.assertEqual(stages[0], "uploaded")
        self.assertIn("aligned", stages)

    def test_the_preview_returns_canonical_column_names(self) -> None:
        body = self.client.get(
            f"/api/v1/dataset-versions/{self.version_id}/preview", params={"limit": 5}
        ).json()

        self.assertTrue(body["available"])
        self.assertIn("turbidity", body["columns"])
        self.assertEqual(len(body["rows"]), 5)

    def test_lineage_starts_empty_and_is_readable(self) -> None:
        body = self.client.get(f"/api/v1/dataset-versions/{self.version_id}/lineage").json()
        self.assertEqual(body["used_by_cases"], [])

    def test_the_field_dictionary_describes_the_data_type(self) -> None:
        body = self.client.get("/api/v1/datasets/field-dictionary/water_quality").json()
        self.assertIn("fields", body)

    def test_freshness_reports_the_modelable_count(self) -> None:
        body = self.client.get("/api/v1/datasets/freshness").json()
        self.assertEqual(body["dataset_count"], 1)
        self.assertEqual(body["modelable_count"], 1)

    def test_versions_are_listed_for_a_dataset(self) -> None:
        body = self.client.get(f"/api/v1/datasets/{self.dataset_id}/versions").json()
        self.assertEqual([item["version_id"] for item in body], [self.version_id])


class LifecycleRouteTest(DatasetApiTestCase):
    def test_a_dataset_can_be_archived_then_deleted(self) -> None:
        dataset_id = self._upload().json()["dataset_id"]

        archived = self.client.post(f"/api/v1/datasets/{dataset_id}/archive")
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(archived.json()["status"], "archived")

        deleted = self.client.delete(f"/api/v1/datasets/{dataset_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["deleted_versions"], 1)
        self.assertEqual(self.client.get(f"/api/v1/datasets/{dataset_id}").status_code, 404)


class AuthGateTest(unittest.TestCase):
    """The dataset routes must sit behind the global auth guard."""

    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_listing_datasets_without_a_token_is_401(self) -> None:
        self.assertEqual(self.client.get("/api/v1/datasets").status_code, 401)

    def test_uploading_without_a_token_is_401(self) -> None:
        response = self.client.post(
            "/api/v1/datasets",
            data={"data_type": "water_quality"},
            files={"file": ("wq.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
