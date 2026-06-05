from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from backend.app.config import get_settings
from backend.app.services.artifact_repository import ArtifactRepository
from backend.app.services.runtime_jobs import RuntimeJobService
from backend.app.services.state_store import SqliteStateStore
from backend.app.schemas import PredictionJobCreateRequest


class FakeProcess:
    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: int | None = None) -> int:
        self.wait_calls += 1
        return 0

    def kill(self) -> None:
        self.killed = True


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
            (artifact_root / "agent").mkdir(parents=True, exist_ok=True)
            (artifact_root / "metrics").mkdir(parents=True, exist_ok=True)
            (artifact_root / "predictions").mkdir(parents=True, exist_ok=True)
            (artifact_root / "agent" / "agent_context.json").write_text("{}", encoding="utf-8")
            (artifact_root / "metrics" / "metrics.json").write_text("{}", encoding="utf-8")
            (artifact_root / "predictions" / "predictions.csv").write_text("target_date\n2024-01-01\n", encoding="utf-8")
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

    def test_completed_status_without_required_artifacts_is_downgraded_to_failed(self) -> None:
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

            run_root = settings.job_runs_root / "job-missing-artifacts"
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
                    "job_id": "job-missing-artifacts",
                    "created_at": "2026-06-05T00:00:00Z",
                    "updated_at": "2026-06-05T00:00:05Z",
                    "status": "running",
                    "artifact_root": str(artifact_root),
                    "status_file": str(status_file),
                }
            )

            refreshed = service.refresh_job("job-missing-artifacts")
            self.assertEqual(refreshed["status"], "failed")
            self.assertEqual(
                refreshed["message"],
                "Job reported completion but required artifacts were missing or unreadable.",
            )

    def test_snapshot_integrated_outputs_rejects_unmanaged_target(self) -> None:
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

            with self.assertRaises(ValueError):
                service._snapshot_integrated_outputs(tmp_root / "not-a-job-run")

    def test_launch_cleanup_terminates_process_when_state_persistence_fails(self) -> None:
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
            fake_process = FakeProcess()

            with patch.object(service, "_spawn_process", return_value=fake_process), patch.object(
                store,
                "append_job",
                side_effect=RuntimeError("database unavailable"),
            ):
                with self.assertRaises(RuntimeError):
                    service.create_prediction_job(
                        PredictionJobCreateRequest(
                            mode="full_pipeline",
                            model_name="cmfbe_stgcn",
                            station_code="2586",
                            use_existing_artifacts=False,
                        )
                    )

            self.assertEqual(service._processes, {})
            self.assertTrue(fake_process.terminated)
            status_files = list(settings.job_runs_root.glob("*/run_status.json"))
            self.assertEqual(len(status_files), 1)
            status_payload = json.loads(status_files[0].read_text(encoding="utf-8"))
            self.assertEqual(status_payload["status"], "failed")
            self.assertIn("state persistence completed", status_payload["message"])


if __name__ == "__main__":
    unittest.main()
