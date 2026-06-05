from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.services.state_store import SqliteStateStore


class SqliteStateStoreTest(unittest.TestCase):
    def test_job_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SqliteStateStore(Path(tmp_dir))
            created = store.append_job(
                {
                    "job_id": "job-1",
                    "created_at": "2026-06-05T00:00:00Z",
                    "status": "running",
                    "model_name": "cmfbe_stgcn",
                    "artifact_root": "X:/artifacts/job-1/outputs",
                }
            )
            self.assertEqual(created["status"], "running")

            updated = store.update_job(
                "job-1",
                {
                    "status": "completed",
                    "finished_at": "2026-06-05T00:10:00Z",
                    "artifact_root": "X:/artifacts/job-1/outputs",
                },
            )
            self.assertEqual(updated["status"], "completed")
            self.assertEqual(store.get_job("job-1")["status"], "completed")
            self.assertEqual(len(store.list_jobs()), 1)


if __name__ == "__main__":
    unittest.main()
