"""The case is what makes a result attributable — these check that it does.

Review items 4 and 5. Two properties matter here and neither was true before:

* a result endpoint called with no case returns 409, instead of quietly serving
  the checked-in research artifacts as if they were the caller's run;
* a case that does answer carries the run id, config hash and staleness of the
  data it was built on.

The app builds its services at import time against the real ``var/`` directory,
so each test swaps in temp-rooted services; nothing here touches the developer's
runtime state.
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
from backend.app.domain.codes import CaseStatus, ErrorCode
from backend.app.services.case_service import CaseService
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


class CaseApiTestCase(unittest.TestCase):
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
        store = SqliteStateStore(settings.state_root)
        self._original_datasets = main.dataset_service
        self._original_cases = main.case_service
        main.dataset_service = DatasetService(settings, store)
        main.case_service = CaseService(settings, store, main.dataset_service)
        self.settings = settings

        main.app.dependency_overrides[main.auth_guard] = admin_auth_guard
        main.app.dependency_overrides[main.current_actor] = lambda: "tester"
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()
        main.dataset_service = self._original_datasets
        main.case_service = self._original_cases
        self._tmp.cleanup()

    def _accepted_version_id(self) -> str:
        response = self.client.post(
            "/api/v1/datasets",
            data={"data_type": "water_quality", "station_code": "2586"},
            files={"file": ("wq.csv", io.BytesIO(_water_quality_csv()), "text/csv")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["version_id"]

    def _create_case(self, **overrides):
        body = {
            "title": "Wusongkou turbidity spike",
            "station_code": "2586",
            "target_date": "2024-02-01",
            "dataset_version_ids": [self._accepted_version_id()],
        }
        body.update(overrides)
        return self.client.post("/api/v1/cases", json=body)


class CaseCreationTest(CaseApiTestCase):
    def test_a_case_records_the_data_it_was_opened_against(self) -> None:
        response = self._create_case()

        self.assertEqual(response.status_code, 201, response.text)
        case = response.json()
        self.assertEqual(case["status"], str(CaseStatus.DRAFT))
        self.assertEqual(case["owner"], "tester")
        self.assertEqual(case["data_quality"]["version_count"], 1)
        self.assertEqual(case["coverage_start"], "2024-01-01")

    def test_a_case_over_an_unusable_dataset_is_refused(self) -> None:
        """A dataset that failed the quality gate cannot become evidence."""
        frame = pd.DataFrame({"监测时间": ["2024-01-01"], "站点": ["2586"], "水温": [15.0]})
        rejected = self.client.post(
            "/api/v1/datasets",
            data={"data_type": "water_quality", "station_code": "2586"},
            files={"file": ("bad.csv", io.BytesIO(frame.to_csv(index=False).encode("utf-8-sig")), "text/csv")},
        ).json()

        response = self._create_case(dataset_version_ids=[rejected["version_id"]])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"], str(ErrorCode.DATASET_NOT_MODELABLE)
        )

    def test_an_unknown_dataset_version_is_refused_with_404_semantics(self) -> None:
        response = self._create_case(dataset_version_ids=["does-not-exist"])

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], str(ErrorCode.NOT_FOUND))

    def test_creating_a_case_records_lineage_on_the_dataset_version(self) -> None:
        version_id = self._accepted_version_id()
        case_id = self._create_case(dataset_version_ids=[version_id]).json()["case_id"]

        lineage = self.client.get(f"/api/v1/dataset-versions/{version_id}/lineage").json()
        self.assertEqual(lineage["used_by_cases"], [case_id])


class CaseReadTest(CaseApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.case = self._create_case().json()
        self.case_id = self.case["case_id"]

    def test_a_case_is_listed_and_fetchable(self) -> None:
        listed = self.client.get("/api/v1/cases").json()
        self.assertEqual([item["case_id"] for item in listed], [self.case_id])

        fetched = self.client.get(f"/api/v1/cases/{self.case_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertFalse(fetched.json()["is_stale"])

    def test_an_unknown_case_is_404_with_a_stable_code(self) -> None:
        response = self.client.get("/api/v1/cases/nope")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], str(ErrorCode.NOT_FOUND))

    def test_the_summary_counts_pending_work(self) -> None:
        body = self.client.get("/api/v1/cases/summary").json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["pending_count"], 1)
        self.assertEqual(body["stale_count"], 0)

    def test_a_case_can_be_retitled(self) -> None:
        response = self.client.patch(
            f"/api/v1/cases/{self.case_id}", json={"title": "Renamed"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Renamed")

    def test_a_case_can_be_archived_then_deleted(self) -> None:
        archived = self.client.post(f"/api/v1/cases/{self.case_id}/archive")
        self.assertEqual(archived.json()["status"], str(CaseStatus.ARCHIVED))

        deleted = self.client.delete(f"/api/v1/cases/{self.case_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/cases/{self.case_id}").status_code, 404)

    def test_a_case_with_no_run_cannot_serve_results(self) -> None:
        response = self.client.get("/api/v1/dashboard", params={"case_id": self.case_id})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"]["code"], str(ErrorCode.CASE_NOT_READY)
        )


class ResultScopeTest(CaseApiTestCase):
    """The core of review item 5: results no longer default to *something*."""

    RESULT_PATHS = (
        "/api/v1/dashboard",
        "/api/v1/diagnostics",
        "/api/v1/scenario-triage",
        "/api/v1/response-playbook",
        "/api/v1/thresholds",
        "/api/v1/boundary",
        "/api/v1/sensitivity",
        "/api/v1/predictions",
    )

    def test_every_result_endpoint_refuses_an_unscoped_read(self) -> None:
        for path in self.RESULT_PATHS:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(
                    response.json()["detail"]["code"], str(ErrorCode.CASE_REQUIRED)
                )

    def test_an_unknown_scope_is_refused_rather_than_ignored(self) -> None:
        response = self.client.get("/api/v1/dashboard", params={"scope": "whatever"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"], str(ErrorCode.VALIDATION_FAILED)
        )

    def test_integrated_artifacts_are_readable_only_when_named_and_are_labelled(self) -> None:
        response = self.client.get("/api/v1/dashboard", params={"scope": "integrated"})

        # The repository may or may not have integrated artifacts on disk; what
        # matters is that the request is not refused for lack of a case, and
        # that a served payload says where it came from.
        self.assertNotEqual(response.status_code, 409)
        if response.status_code == 200:
            provenance = response.json()["provenance"]
            self.assertEqual(provenance["scope"], "integrated")
            self.assertTrue(provenance["is_integrated_default"])

    def test_meta_still_answers_without_a_case(self) -> None:
        """The app shell needs the station profile before any case exists."""
        response = self.client.get("/api/v1/meta")
        self.assertNotEqual(response.status_code, 409)


class CaseRunTest(CaseApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.case_id = self._create_case().json()["case_id"]

    def test_a_date_range_outside_the_case_data_is_refused_at_submit(self) -> None:
        """Review item 1: an impossible request fails now, not after training."""
        response = self.client.post(
            f"/api/v1/cases/{self.case_id}/run",
            json={"model_name": "cmfbe_stgcn", "start_date": "2019-01-01"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"], str(ErrorCode.DATE_RANGE_OUT_OF_COVERAGE)
        )

    def test_a_backwards_date_range_is_refused(self) -> None:
        response = self.client.post(
            f"/api/v1/cases/{self.case_id}/run",
            json={"start_date": "2024-02-01", "end_date": "2024-01-15"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"], str(ErrorCode.VALIDATION_FAILED)
        )

    def test_running_a_missing_case_is_404(self) -> None:
        response = self.client.post("/api/v1/cases/nope/run", json={})
        self.assertEqual(response.status_code, 404)


class CaseProvenanceTest(CaseApiTestCase):
    """Provenance is computed from the case record, so it is testable without
    launching the real pipeline."""

    def setUp(self) -> None:
        super().setUp()
        self.case_id = self._create_case().json()["case_id"]

    def _mark_completed(self, *, generated_at: str = "2030-01-01T00:00:00Z") -> None:
        main.case_service.update_case(
            self.case_id,
            {
                "status": str(CaseStatus.READY),
                "job_id": "job-abc",
                "run_id": "job-abc",
                "model_version": "cmfbe_stgcn",
                "config_hash": "deadbeefcafe0001",
                "artifacts_generated_at": generated_at,
            },
        )

    def test_provenance_carries_the_run_identity(self) -> None:
        self._mark_completed()

        body = self.client.get(f"/api/v1/cases/{self.case_id}/provenance").json()

        self.assertEqual(body["run_id"], "job-abc")
        self.assertEqual(body["model_version"], "cmfbe_stgcn")
        self.assertEqual(body["config_hash"], "deadbeefcafe0001")
        self.assertEqual(body["scope"], "case")
        self.assertFalse(body["is_stale"])

    def test_artifacts_older_than_their_input_data_are_marked_stale(self) -> None:
        """Review item 5: a result predating its data must say so."""
        self._mark_completed(generated_at="2000-01-01T00:00:00Z")

        body = self.client.get(f"/api/v1/cases/{self.case_id}/provenance").json()

        self.assertTrue(body["is_stale"])
        self.assertEqual(body["stale_reason"], "input_dataset_newer")

    def test_a_stale_case_moves_out_of_ready(self) -> None:
        self._mark_completed(generated_at="2000-01-01T00:00:00Z")

        self.client.get(f"/api/v1/cases/{self.case_id}/provenance")

        case = main.case_service.get_case(self.case_id)
        self.assertEqual(case["status"], str(CaseStatus.STALE))

    def test_a_case_cited_by_a_report_cannot_be_deleted(self) -> None:
        main.case_service.attach_report(self.case_id, "report-1")

        response = self.client.delete(f"/api/v1/cases/{self.case_id}")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"]["code"], str(ErrorCode.INVALID_STATE_TRANSITION)
        )


class CaseAuthGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_listing_cases_without_a_token_is_401(self) -> None:
        self.assertEqual(self.client.get("/api/v1/cases").status_code, 401)

    def test_reading_results_without_a_token_is_401_not_409(self) -> None:
        """The auth gate runs before scope resolution."""
        self.assertEqual(self.client.get("/api/v1/dashboard").status_code, 401)


if __name__ == "__main__":
    unittest.main()
