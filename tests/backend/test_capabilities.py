"""The deployment's vocabulary and the cross-modal satellite view.

Two data-layer contracts:

* ``/api/v1/capabilities`` reports the registries the frontend builds its
  selectors from, so nothing in the UI has to hard-code a data type, model,
  severity or station.
* ``/api/v1/cross-modal/zhangjiabang`` describes each UAV asset and, for a
  video, the representative frames it was sliced into — the frontend renders
  those, so the slicing has to survive the API.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.app import main
from tests.backend._helpers import admin_auth_guard


class CapabilitiesTest(unittest.TestCase):
    def setUp(self) -> None:
        main.app.dependency_overrides[main.auth_guard] = admin_auth_guard
        main.app.dependency_overrides[main.current_actor] = lambda: "tester"
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()

    def test_capabilities_describes_the_registries(self) -> None:
        response = self.client.get("/api/v1/capabilities")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        self.assertIn("water_quality", {item["key"] for item in body["data_types"]})
        self.assertIn("cmfbe_stgcn", {item["key"] for item in body["models"]})
        self.assertIn("critical", body["severities"])
        self.assertIn("html", body["report_formats"])
        self.assertIn("turbidity", {item["key"] for item in body["indicators"]})
        self.assertIn("published", body["model_transitions"])
        self.assertTrue(body["stations"])

    def test_cross_modal_slices_a_video_into_frames(self) -> None:
        response = self.client.get("/api/v1/cross-modal/zhangjiabang")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        videos = [asset for asset in body["preview_assets"] if asset["media_type"] == "video"]
        self.assertTrue(videos)
        frames = videos[0]["representative_frames"]
        self.assertTrue(frames)
        self.assertTrue(all("/api/v1/cross-modal/media" in frame for frame in frames))


if __name__ == "__main__":
    unittest.main()
