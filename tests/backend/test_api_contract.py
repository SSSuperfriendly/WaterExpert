from __future__ import annotations

import unittest

from backend.app.main import app


class ApiContractTest(unittest.TestCase):
    def test_expected_routes_are_registered(self) -> None:
        registered = {route.path for route in app.routes}
        expected = {
            "/healthz",
            "/api/v1/auth/login",
            "/api/v1/auth/hint",
            "/api/v1/meta",
            "/api/v1/stations",
            "/api/v1/data/import",
            "/api/v1/data/upload",
            "/api/v1/data/imports",
            "/api/v1/database/summary",
            "/api/v1/database/stations",
            "/api/v1/database/query",
            "/api/v1/preprocess/summary",
            "/api/v1/visualization/summary",
            "/api/v1/prediction-jobs",
            "/api/v1/prediction-jobs/{job_id}",
            "/api/v1/prediction-jobs/{job_id}/series",
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
        }
        missing = expected - registered
        self.assertEqual(missing, set(), f"Missing registered routes: {missing}")

    def test_api_routes_are_versioned(self) -> None:
        api_paths = [route.path for route in app.routes if route.path.startswith("/api/")]
        self.assertTrue(api_paths)
        self.assertTrue(all(path.startswith("/api/v1/") for path in api_paths))


if __name__ == "__main__":
    unittest.main()
