from __future__ import annotations

import json
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
            self.assertTrue(
                (Path(record["artifact_root"]) / "predictions" / "predictions.csv").exists()
            )
            scoped_repo = service.get_job_repository(record["job_id"], require_completed=True)
            payload = scoped_repo.predictions(model="cmfbe_stgcn", split="test")
            self.assertGreater(len(payload["series"]), 0)

    def test_completed_status_file_message_overrides_stale_running_message(self) -> None:
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

            run_root = settings.job_runs_root / "job-completed"
            artifact_root = run_root / "outputs"
            status_file = run_root / "run_status.json"
            run_root.mkdir(parents=True, exist_ok=True)
            artifact_root.mkdir(parents=True, exist_ok=True)
            status_file.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "started_at": "2026-06-05T00:00:00Z",
                        "finished_at": "2026-06-05T00:10:00Z",
                        "return_code": 0,
                        "message": "Job completed with verified job-scoped artifacts.",
                    }
                ),
                encoding="utf-8",
            )
            store.append_job(
                {
                    "job_id": "job-completed",
                    "created_at": "2026-06-05T00:00:00Z",
                    "updated_at": "2026-06-05T00:00:05Z",
                    "status": "running",
                    "message": "Job is still running in detached mode; waiting for status file completion.",
                    "artifact_root": str(artifact_root),
                    "status_file": str(status_file),
                }
            )

            refreshed = service.refresh_job("job-completed")
            self.assertEqual(refreshed["status"], "completed")
            self.assertEqual(
                refreshed["message"],
                "Job completed with verified job-scoped artifacts.",
            )

    def test_failed_terminal_status_does_not_attach_artifact_manifest(self) -> None:
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

            run_root = settings.job_runs_root / "job-failed"
            artifact_root = run_root / "outputs"
            status_file = run_root / "run_status.json"
            run_root.mkdir(parents=True, exist_ok=True)
            artifact_root.mkdir(parents=True, exist_ok=True)
            status_file.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "started_at": "2026-06-05T00:00:00Z",
                        "finished_at": "2026-06-05T00:03:00Z",
                        "return_code": -1,
                        "message": "Job failed during pipeline orchestration.",
                        "error": "CalledProcessError: synthetic failure",
                    }
                ),
                encoding="utf-8",
            )
            store.append_job(
                {
                    "job_id": "job-failed",
                    "created_at": "2026-06-05T00:00:00Z",
                    "updated_at": "2026-06-05T00:00:05Z",
                    "status": "running",
                    "artifact_root": str(artifact_root),
                    "status_file": str(status_file),
                }
            )

            refreshed = service.refresh_job("job-failed")
            self.assertEqual(refreshed["status"], "failed")
            self.assertNotIn("artifacts", refreshed)


if __name__ == "__main__":
    unittest.main()
