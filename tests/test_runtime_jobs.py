from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from backend.app.config import get_settings
from backend.app.services.artifact_repository import ArtifactRepository
from backend.app.services.runtime_jobs import RuntimeJobService
from backend.app.services.state_store import SqliteStateStore
from backend.app.schemas import PredictionJobCreateRequest


class RuntimeJobsTest(unittest.TestCase):
    def test_existing_artifact_job_creates_scoped_snapshot(self) -> None:
        base_settings = get_settings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            settings = replace(
                base_settings,
                state_root=tmp_root / "state",
                report_root=tmp_root / "reports",
            )
            repository = ArtifactRepository(settings)
            store = SqliteStateStore(settings.state_root)
            service = RuntimeJobService(settings, repository, store)

            record = service.create_prediction_job(
                PredictionJobCreateRequest(
                    mode="inference",
                    model_name="cmfbe_stgcn",
                    station_code="2586",
                    use_existing_artifacts=True,
                )
            )

            self.assertEqual(record["status"], "completed")
            self.assertNotEqual(Path(record["artifact_root"]), settings.outputs_root)
            self.assertTrue((Path(record["artifact_root"]) / "predictions" / "predictions.csv").exists())
            scoped_repo = service.get_job_repository(record["job_id"], require_completed=True)
            payload = scoped_repo.predictions(model="cmfbe_stgcn", split="test")
            self.assertGreater(len(payload["series"]), 0)


if __name__ == "__main__":
    unittest.main()
