from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class SqliteStateStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "app_state.sqlite3"
        self.imports_path = self.root / "data_imports.json"
        self.jobs_path = self.root / "prediction_jobs.json"
        self._initialize()
        self._migrate_legacy_json()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def _session(self) -> sqlite3.Connection:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_imports (
                    import_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT,
                    source_name TEXT,
                    data_type TEXT,
                    station_code TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_data_imports_created_at
                    ON data_imports(created_at DESC);

                CREATE TABLE IF NOT EXISTS prediction_jobs (
                    job_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT,
                    model_name TEXT,
                    station_code TEXT,
                    artifact_root TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_prediction_jobs_created_at
                    ON prediction_jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_prediction_jobs_status
                    ON prediction_jobs(status);
                """
            )

    def _meta_value(self, key: str) -> str | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = ?", (key,)
            ).fetchone()
        return None if row is None else str(row["value"])

    def _set_meta_value(self, key: str, value: str) -> None:
        with self._session() as connection:
            connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def _migrate_legacy_json(self) -> None:
        if self._meta_value("legacy_json_migrated") == "1":
            return

        for path, table in (
            (self.imports_path, "data_imports"),
            (self.jobs_path, "prediction_jobs"),
        ):
            if not path.exists():
                continue
            try:
                records = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                if table == "data_imports" and record.get("import_id"):
                    self._upsert_import_record(record, replace=False)
                if table == "prediction_jobs" and record.get("job_id"):
                    self._upsert_job_record(record, replace=False)

        self._set_meta_value("legacy_json_migrated", "1")

    def _upsert_import_record(self, record: dict[str, Any], replace: bool) -> None:
        payload = json.dumps(record, ensure_ascii=False)
        conflict = (
            "ON CONFLICT(import_id) DO UPDATE SET "
            "created_at = excluded.created_at, "
            "status = excluded.status, "
            "source_name = excluded.source_name, "
            "data_type = excluded.data_type, "
            "station_code = excluded.station_code, "
            "payload_json = excluded.payload_json"
        )
        sql = (
            "INSERT INTO data_imports(import_id, created_at, status, source_name, data_type, station_code, payload_json) "
            "VALUES(?, ?, ?, ?, ?, ?, ?) "
        )
        if replace:
            sql += conflict
        else:
            sql += "ON CONFLICT(import_id) DO NOTHING"
        with self._session() as connection:
            connection.execute(
                sql,
                (
                    str(record["import_id"]),
                    str(record.get("created_at", "")),
                    record.get("status"),
                    record.get("source_name"),
                    record.get("data_type"),
                    record.get("station_code"),
                    payload,
                ),
            )

    def _upsert_job_record(self, record: dict[str, Any], replace: bool) -> None:
        payload = json.dumps(record, ensure_ascii=False)
        updated_at = str(record.get("updated_at") or record.get("finished_at") or record.get("created_at") or "")
        conflict = (
            "ON CONFLICT(job_id) DO UPDATE SET "
            "created_at = excluded.created_at, "
            "updated_at = excluded.updated_at, "
            "status = excluded.status, "
            "model_name = excluded.model_name, "
            "station_code = excluded.station_code, "
            "artifact_root = excluded.artifact_root, "
            "payload_json = excluded.payload_json"
        )
        sql = (
            "INSERT INTO prediction_jobs(job_id, created_at, updated_at, status, model_name, station_code, artifact_root, payload_json) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
        )
        if replace:
            sql += conflict
        else:
            sql += "ON CONFLICT(job_id) DO NOTHING"
        with self._session() as connection:
            connection.execute(
                sql,
                (
                    str(record["job_id"]),
                    str(record.get("created_at", "")),
                    updated_at,
                    record.get("status"),
                    record.get("model_name"),
                    record.get("station_code"),
                    record.get("artifact_root"),
                    payload,
                ),
            )

    def _decode_rows(self, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [json.loads(str(row["payload_json"])) for row in rows]

    def list_imports(self) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM data_imports ORDER BY created_at DESC"
            ).fetchall()
        return self._decode_rows(rows)

    def append_import(self, record: dict[str, Any]) -> dict[str, Any]:
        self._upsert_import_record(record, replace=True)
        return record

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM prediction_jobs ORDER BY created_at DESC"
            ).fetchall()
        return self._decode_rows(rows)

    def append_job(self, record: dict[str, Any]) -> dict[str, Any]:
        if "updated_at" not in record:
            record = {**record, "updated_at": record.get("created_at", "")}
        self._upsert_job_record(record, replace=True)
        return record

    def update_job(self, job_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get_job(job_id)
        if current is None:
            raise KeyError(job_id)
        updated = {**current, **updates}
        if "updated_at" not in updated:
            updated["updated_at"] = str(
                updates.get("finished_at")
                or updates.get("started_at")
                or updates.get("created_at")
                or current.get("updated_at")
                or current.get("created_at")
                or ""
            )
        self._upsert_job_record(updated, replace=True)
        return updated

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT payload_json FROM prediction_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["payload_json"]))
