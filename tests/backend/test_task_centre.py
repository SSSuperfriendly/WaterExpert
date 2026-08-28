"""The task centre service surface: queue, cancel, retry, retention, logs.

Review item 10. These exercise the service methods that the new routes expose,
against a seeded state store, so no pipeline process has to run.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from backend.app.config import get_settings
from backend.app.domain.codes import ErrorCode, JobStatus
from backend.app.services.artifact_repository import ArtifactRepository
from backend.app.services.runtime_jobs import (
    DEFAULT_JOB_PRIORITY,
    JobParameterError,
    RuntimeJobService,
)
from backend.app.services.state_store import SqliteStateStore


def _utc(days_ago: int) -> str:
    stamp = datetime.now(timezone.utc).timestamp() - days_ago * 86400
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace("+00:00", "Z")


class TaskCentreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        settings = replace(
            get_settings(),
            state_root=root / "state",
            report_root=root / "reports",
            max_concurrent_jobs=1,
            job_timeout_seconds=3600,
            job_run_retention_days=30,
        )
        self.store = SqliteStateStore(settings.state_root)
        self.service = RuntimeJobService(settings, ArtifactRepository(settings), self.store)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self, job_id: str, status: str, **extra) -> dict:
        record = {
            "job_id": job_id,
            "status": status,
            "created_at": _utc(0),
            "queued_at": _utc(0),
            "priority": DEFAULT_JOB_PRIORITY,
            "config_snapshot_path": "",
            **extra,
        }
        return self.store.append_job(record)

    def test_queue_snapshot_reports_quota_and_slots(self) -> None:
        self._seed("a", str(JobStatus.RUNNING))
        snapshot = self.service.queue_snapshot()

        self.assertEqual(snapshot["max_concurrent_jobs"], 1)
        self.assertEqual(snapshot["running"], 1)
        self.assertEqual(snapshot["queued"], 0)
        self.assertEqual(snapshot["free_slots"], 0)

    def test_cancelling_a_queued_job_is_immediate(self) -> None:
        self._seed("q", str(JobStatus.QUEUED))

        cancelled = self.service.cancel_job("q")

        self.assertEqual(cancelled["status"], str(JobStatus.CANCELLED))

    def test_a_finished_job_cannot_be_cancelled(self) -> None:
        self._seed("done", str(JobStatus.COMPLETED))

        with self.assertRaises(JobParameterError) as ctx:
            self.service.cancel_job("done")
        self.assertEqual(ctx.exception.code, ErrorCode.JOB_NOT_CANCELLABLE)

    def test_an_active_job_cannot_be_retried_without_cancelling(self) -> None:
        self._seed("live", str(JobStatus.RUNNING), started_at=_utc(0))

        with self.assertRaises(JobParameterError) as ctx:
            self.service.retry_job("live")
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_STATE_TRANSITION)

    def test_a_queued_job_is_cancelled_not_retried(self) -> None:
        self._seed("q2", str(JobStatus.QUEUED))
        with self.assertRaises(JobParameterError):
            self.service.retry_job("q2")

    def test_log_stream_name_is_validated(self) -> None:
        self._seed("j", str(JobStatus.COMPLETED), stdout_log="/nonexistent/out.log")

        # 'stderr' is a valid stream name, but the job has none on record; the
        # absence is reported, not silently mapped to another file.
        with self.assertRaises(FileNotFoundError):
            self.service.log_path("j", "stderr")

    def test_log_path_rejects_an_unknown_stream_name(self) -> None:
        self._seed("j", str(JobStatus.COMPLETED), stdout_log="/nonexistent/out.log")

        with self.assertRaises(JobParameterError):
            self.service.log_path("j", "../../etc/passwd")

    def test_purge_removes_only_expired_terminal_runs(self) -> None:
        self._seed("old", str(JobStatus.COMPLETED), finished_at=_utc(40))
        self._seed("recent", str(JobStatus.COMPLETED), finished_at=_utc(1))
        self._seed("running", str(JobStatus.RUNNING), finished_at=_utc(40))

        result = self.service.purge_expired_jobs()

        self.assertIn("old", result["removed"])
        self.assertNotIn("recent", result["removed"])
        self.assertNotIn("running", result["removed"])
        self.assertIsNone(self.store.get_job("old"))

    def test_purge_respects_a_disabled_retention_window(self) -> None:
        self.service.settings = replace(self.service.settings, job_run_retention_days=0)
        self._seed("keep", str(JobStatus.COMPLETED), finished_at=_utc(40))

        result = self.service.purge_expired_jobs()

        self.assertEqual(result["skipped"], "retention_disabled")
        self.assertIsNotNone(self.store.get_job("keep"))


if __name__ == "__main__":
    unittest.main()
