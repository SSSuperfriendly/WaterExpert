from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sqlite3

from backend.app.services.state_store import (
    CASES_TABLE,
    DATASETS_TABLE,
    JOBS_TABLE,
    SqliteStateStore,
)


class SchemaMigrationTest(unittest.TestCase):
    def test_adds_new_columns_to_a_pre_existing_table(self) -> None:
        """An older database must gain the new columns before indexes touch them."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            legacy = sqlite3.connect(root / "app_state.sqlite3")
            try:
                legacy.execute(
                    "CREATE TABLE prediction_jobs ("
                    "job_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
                    "updated_at TEXT NOT NULL, status TEXT, payload_json TEXT NOT NULL)"
                )
                legacy.execute(
                    "INSERT INTO prediction_jobs VALUES(?, ?, ?, ?, ?)",
                    (
                        "old-job",
                        "2026-01-01T00:00:00Z",
                        "2026-01-01T00:00:00Z",
                        "completed",
                        '{"job_id": "old-job", "status": "completed"}',
                    ),
                )
                legacy.commit()
            finally:
                legacy.close()

            store = SqliteStateStore(root)

            self.assertEqual(store.get_job("old-job")["status"], "completed")
            store.update_job("old-job", {"case_id": "case-9", "priority": "5"})
            self.assertEqual(store.list(JOBS_TABLE, filters={"case_id": "case-9"})[0]["job_id"], "old-job")

    def test_every_declared_table_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SqliteStateStore(Path(tmp_dir))
            for table in (JOBS_TABLE, DATASETS_TABLE, CASES_TABLE):
                self.assertEqual(store.list(table), [])


class GenericRecordTableTest(unittest.TestCase):
    def test_insert_get_update_list_delete_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SqliteStateStore(Path(tmp_dir))
            store.insert(
                CASES_TABLE,
                {"case_id": "c1", "created_at": "2026-01-01T00:00:00Z", "status": "draft"},
            )
            store.insert(
                CASES_TABLE,
                {"case_id": "c2", "created_at": "2026-01-02T00:00:00Z", "status": "ready"},
            )

            self.assertEqual(store.count(CASES_TABLE), 2)
            self.assertEqual(store.get(CASES_TABLE, "c1")["status"], "draft")
            self.assertEqual(len(store.list(CASES_TABLE, filters={"status": "ready"})), 1)
            self.assertEqual(
                len(store.list(CASES_TABLE, filters={"status": ["draft", "ready"]})), 2
            )
            self.assertEqual(store.update(CASES_TABLE, "c1", {"status": "ready"})["status"], "ready")
            self.assertTrue(store.delete(CASES_TABLE, "c1"))
            self.assertIsNone(store.get(CASES_TABLE, "c1"))

    def test_filtering_on_an_unprojected_column_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SqliteStateStore(Path(tmp_dir))
            with self.assertRaises(ValueError):
                store.list(CASES_TABLE, filters={"not_a_column": "x"})


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
