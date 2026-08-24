from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Iterator

SCHEMA_META_TABLE = "schema_meta"
IMPORTS_TABLE = "data_imports"
JOBS_TABLE = "prediction_jobs"
LEGACY_MIGRATION_META_KEY = "legacy_json_migrated"
SQLITE_TIMEOUT_MS = 30000
SQLITE_TIMEOUT_SECONDS = SQLITE_TIMEOUT_MS / 1000
CORRUPT_RECORD_STATUS = "corrupt"


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
        connection = sqlite3.connect(
            self.db_path,
            timeout=SQLITE_TIMEOUT_SECONDS,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(f"PRAGMA busy_timeout = {SQLITE_TIMEOUT_MS}")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def _session(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except Exception:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._session(write=True) as connection:
            connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {SCHEMA_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS {IMPORTS_TABLE} (
                    import_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT,
                    source_name TEXT,
                    data_type TEXT,
                    station_code TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_data_imports_created_at
                    ON {IMPORTS_TABLE}(created_at DESC);

                CREATE TABLE IF NOT EXISTS {JOBS_TABLE} (
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
                    ON {JOBS_TABLE}(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_prediction_jobs_status
                    ON {JOBS_TABLE}(status);
                """
            )

    def _meta_value(self, key: str) -> str | None:
        with self._session() as connection:
            row = connection.execute(
                f"SELECT value FROM {SCHEMA_META_TABLE} WHERE key = ?", (key,)
            ).fetchone()
        return None if row is None else str(row["value"])

    def _set_meta_value(self, key: str, value: str) -> None:
        with self._session(write=True) as connection:
            connection.execute(
                f"INSERT INTO {SCHEMA_META_TABLE}(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def _migrate_legacy_json(self) -> None:
        if self._meta_value(LEGACY_MIGRATION_META_KEY) == "1":
            return

        for path, record_kind in (
            (self.imports_path, "import"),
            (self.jobs_path, "job"),
        ):
            for record in self._read_legacy_records(path):
                if record_kind == "import" and record.get("import_id"):
                    self._upsert_import_record(record, replace=False)
                elif record_kind == "job" and record.get("job_id"):
                    self._upsert_job_record(record, replace=False)

        self._set_meta_value(LEGACY_MIGRATION_META_KEY, "1")

    def _read_legacy_records(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        return [record for record in payload if isinstance(record, dict)]

    def _job_updated_at(self, record: dict[str, Any]) -> str:
        return str(
            record.get("updated_at")
            or record.get("finished_at")
            or record.get("created_at")
            or ""
        )

    def _normalize_job_record(self, record: dict[str, Any]) -> dict[str, Any]:
        if "updated_at" in record:
            return record
        return {**record, "updated_at": self._job_updated_at(record)}

    def _corrupt_record_view(
        self,
        *,
        primary_key: str,
        primary_value: Any,
        message: str,
    ) -> dict[str, Any]:
        return {
            primary_key: primary_value,
            "status": CORRUPT_RECORD_STATUS,
            "message": message,
        }

    def _load_json_payload(self, payload_json: str, *, key: str, key_value: Any) -> dict[str, Any]:
        try:
            payload = json.loads(payload_json)
        except (TypeError, JSONDecodeError) as exc:
            raise ValueError(f"Corrupt state payload for {key}={key_value}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected state payload type for {key}={key_value}.")
        return payload

    def _execute_import_upsert(
        self,
        connection: sqlite3.Connection,
        record: dict[str, Any],
        *,
        replace: bool,
    ) -> None:
        payload = json.dumps(record, ensure_ascii=False)
        sql = (
            f"INSERT INTO {IMPORTS_TABLE}(import_id, created_at, status, source_name, data_type, station_code, payload_json) "
            "VALUES(?, ?, ?, ?, ?, ?, ?) "
        )
        if replace:
            sql += (
                "ON CONFLICT(import_id) DO UPDATE SET "
                "created_at = excluded.created_at, "
                "status = excluded.status, "
                "source_name = excluded.source_name, "
                "data_type = excluded.data_type, "
                "station_code = excluded.station_code, "
                "payload_json = excluded.payload_json"
            )
        else:
            sql += "ON CONFLICT(import_id) DO NOTHING"
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

    def _execute_job_upsert(
        self,
        connection: sqlite3.Connection,
        record: dict[str, Any],
        *,
        replace: bool,
    ) -> None:
        normalized = self._normalize_job_record(record)
        payload = json.dumps(normalized, ensure_ascii=False)
        sql = (
            f"INSERT INTO {JOBS_TABLE}(job_id, created_at, updated_at, status, model_name, station_code, artifact_root, payload_json) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
        )
        if replace:
            sql += (
                "ON CONFLICT(job_id) DO UPDATE SET "
                "created_at = excluded.created_at, "
                "updated_at = excluded.updated_at, "
                "status = excluded.status, "
                "model_name = excluded.model_name, "
                "station_code = excluded.station_code, "
                "artifact_root = excluded.artifact_root, "
                "payload_json = excluded.payload_json"
            )
        else:
            sql += "ON CONFLICT(job_id) DO NOTHING"
        connection.execute(
            sql,
            (
                str(normalized["job_id"]),
                str(normalized.get("created_at", "")),
                self._job_updated_at(normalized),
                normalized.get("status"),
                normalized.get("model_name"),
                normalized.get("station_code"),
                normalized.get("artifact_root"),
                payload,
            ),
        )

    def _upsert_import_record(self, record: dict[str, Any], replace: bool) -> None:
        with self._session(write=True) as connection:
            self._execute_import_upsert(connection, record, replace=replace)

    def _upsert_job_record(self, record: dict[str, Any], replace: bool) -> None:
        with self._session(write=True) as connection:
            self._execute_job_upsert(connection, record, replace=replace)

    def _decode_payload_row(self, row: sqlite3.Row, primary_key: str) -> dict[str, Any]:
        try:
            return self._load_json_payload(
                str(row["payload_json"]),
                key=primary_key,
                key_value=row[primary_key],
            )
        except Exception as exc:
            return self._corrupt_record_view(
                primary_key=primary_key,
                primary_value=row[primary_key],
                message=f"Corrupt state payload: {type(exc).__name__}: {exc}",
            )

    def list_imports(self) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                f"SELECT import_id, payload_json FROM {IMPORTS_TABLE} ORDER BY created_at DESC"
            ).fetchall()
        return [self._decode_payload_row(row, "import_id") for row in rows]

    def append_import(self, record: dict[str, Any]) -> dict[str, Any]:
        self._upsert_import_record(record, replace=True)
        return record

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                f"SELECT job_id, payload_json FROM {JOBS_TABLE} ORDER BY created_at DESC"
            ).fetchall()
        return [self._decode_payload_row(row, "job_id") for row in rows]

    def append_job(self, record: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_job_record(record)
        self._upsert_job_record(normalized, replace=True)
        return normalized

    def update_job(self, job_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self._session(write=True) as connection:
            row = connection.execute(
                f"SELECT payload_json FROM {JOBS_TABLE} WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            current = self._load_json_payload(
                str(row["payload_json"]),
                key="job_id",
                key_value=job_id,
            )
            updated = {**current, **updates}
            if "updated_at" not in updated:
                updated["updated_at"] = self._job_updated_at({**current, **updates})
            self._execute_job_upsert(connection, updated, replace=True)
            return updated

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute(
                f"SELECT job_id, payload_json FROM {JOBS_TABLE} WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return self._decode_payload_row(row, "job_id")
