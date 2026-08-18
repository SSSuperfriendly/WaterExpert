from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sqlite3

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

    def test_update_job_rejects_corrupt_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = SqliteStateStore(root)
            connection = sqlite3.connect(store.db_path)
            try:
                connection.execute(
                    "INSERT INTO prediction_jobs(job_id, created_at, updated_at, payload_json) VALUES(?, ?, ?, ?)",
                    ("job-corrupt", "2026-06-05T00:00:00Z", "2026-06-05T00:00:00Z", "{"),
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(ValueError):
                store.update_job("job-corrupt", {"status": "failed"})

    def test_get_job_marks_non_mapping_payload_as_corrupt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = SqliteStateStore(root)
            connection = sqlite3.connect(store.db_path)
            try:
                connection.execute(
                    "INSERT INTO prediction_jobs(job_id, created_at, updated_at, payload_json) VALUES(?, ?, ?, ?)",
                    ("job-list", "2026-06-05T00:00:00Z", "2026-06-05T00:00:00Z", "[]"),
                )
                connection.commit()
            finally:
                connection.close()

            payload = store.get_job("job-list")
            self.assertEqual(payload["status"], "corrupt")
            self.assertIn("Unexpected state payload type", payload["message"])


if __name__ == "__main__":
    unittest.main()
