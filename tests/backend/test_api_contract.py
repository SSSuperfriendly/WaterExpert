from __future__ import annotations

import unittest

from backend.app.main import app


class ApiContractTest(unittest.TestCase):
    @staticmethod
    def _registered_paths() -> list[str]:
        """Paths of every directly-registered route.

        FastAPI >= 0.141 appends a lazy ``_IncludedRouter`` placeholder for each
        ``include_router`` call instead of flattening the child routes, and that
        placeholder has no ``.path``. The contract below only covers routes this
        module declares itself, so the placeholders are skipped.
        """
        return [route.path for route in app.routes if hasattr(route, "path")]

    def test_expected_routes_are_registered(self) -> None:
        registered = set(self._registered_paths())
        expected = {
            "/healthz",
            "/readyz",
            "/api/v1/health/dependencies",
            "/api/v1/health/model",
            "/api/v1/health/data",
            "/api/v1/admin/maintenance/cleanup",
            "/api/v1/auth/login",
            "/api/v1/auth/hint",
            "/api/v1/meta",
            "/api/v1/stations",
            "/api/v1/datasets",
            "/api/v1/datasets/import",
            "/api/v1/datasets/freshness",
            "/api/v1/datasets/quality-alerts",
            "/api/v1/datasets/field-dictionary/{data_type}",
            "/api/v1/datasets/{dataset_id}",
            "/api/v1/datasets/{dataset_id}/archive",
            "/api/v1/datasets/{dataset_id}/versions",
            "/api/v1/dataset-versions/{version_id}",
            "/api/v1/dataset-versions/{version_id}/quality",
            "/api/v1/dataset-versions/{version_id}/preview",
            "/api/v1/dataset-versions/{version_id}/lineage",
            "/api/v1/database/summary",
            "/api/v1/database/stations",
            "/api/v1/database/query",
            "/api/v1/preprocess/summary",
            "/api/v1/visualization/summary",
            "/api/v1/prediction-jobs",
            "/api/v1/prediction-jobs/queue",
            "/api/v1/prediction-jobs/{job_id}",
            "/api/v1/prediction-jobs/{job_id}/series",
            "/api/v1/prediction-jobs/{job_id}/cancel",
            "/api/v1/prediction-jobs/{job_id}/retry",
            "/api/v1/prediction-jobs/{job_id}/artifacts",
            "/api/v1/prediction-jobs/{job_id}/logs/{stream}",
            "/api/v1/cases",
            "/api/v1/cases/summary",
            "/api/v1/cases/{case_id}",
            "/api/v1/cases/{case_id}/archive",
            "/api/v1/cases/{case_id}/provenance",
            "/api/v1/cases/{case_id}/run",
            "/api/v1/models",
            "/api/v1/models/summary",
            "/api/v1/models/current",
            "/api/v1/models/{model_version_id}",
            "/api/v1/models/{model_version_id}/transition",
            "/api/v1/reports",
            "/api/v1/reports/summary",
            "/api/v1/reports/{report_id}",
            "/api/v1/reports/{report_id}/submit",
            "/api/v1/reports/{report_id}/review",
            "/api/v1/reports/{report_id}/generate",
            "/api/v1/reports/{report_id}/archive",
            "/api/v1/events",
            "/api/v1/events/summary",
            "/api/v1/events/{event_id}",
            "/api/v1/events/{event_id}/assign",
            "/api/v1/events/{event_id}/acknowledge",
            "/api/v1/events/{event_id}/handle",
            "/api/v1/events/{event_id}/review",
            "/api/v1/events/{event_id}/close",
            "/api/v1/events/{event_id}/false-positive",
            "/api/v1/events/{event_id}/escalate",
            "/api/v1/dashboard",
            "/api/v1/predictions",
            "/api/v1/diagnostics",
            "/api/v1/scenario-triage",
            "/api/v1/response-playbook",
            "/api/v1/thresholds",
            "/api/v1/boundary",
            "/api/v1/sensitivity",
            "/api/v1/realtime-validation",
            "/api/v1/cross-modal/zhangjiabang",
            "/api/v1/cross-modal/media",
            "/api/v1/report/export",
            "/api/v1/report/files/{filename}",
            "/api/v1/knowledge-graph/summary",
            "/api/v1/knowledge-graph/upload",
            "/api/v1/knowledge-graph/uploads",
            "/api/v1/knowledge-graph/uploads/clear",
            "/api/v1/knowledge-graph/preprocess",
            "/api/v1/knowledge-graph/texts",
            "/api/v1/knowledge-graph/texts/clear",
            "/api/v1/knowledge-graph/build",
            "/api/v1/knowledge-graph/jobs",
            "/api/v1/knowledge-graph/jobs/{job_id}",
            "/api/v1/knowledge-graph/graph",
            "/api/v1/knowledge-graph/kg/clear",
            "/api/v1/knowledge-graph/qa",
            "/api/v1/knowledge-graph/files/{name}",
            "/api/v1/agent/health",
            "/api/v1/agent/scenarios",
            "/api/v1/agent/strategy",
            "/api/v1/agent/strategy/{job_id}",
        }
        missing = expected - registered
        self.assertEqual(missing, set(), f"Missing registered routes: {missing}")

    def test_api_routes_are_versioned(self) -> None:
        api_paths = [path for path in self._registered_paths() if path.startswith("/api/")]
        self.assertTrue(api_paths)
        self.assertTrue(all(path.startswith("/api/v1/") for path in api_paths))


if __name__ == "__main__":
    unittest.main()
