from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Iterator

SCHEMA_META_TABLE = "schema_meta"
IMPORTS_TABLE = "data_imports"
JOBS_TABLE = "prediction_jobs"
DATASETS_TABLE = "datasets"
DATASET_VERSIONS_TABLE = "dataset_versions"
CASES_TABLE = "cases"
MODEL_REGISTRY_TABLE = "model_registry"
REPORTS_TABLE = "reports"
EVENTS_TABLE = "events"
AUDIT_EVENTS_TABLE = "audit_events"

LEGACY_MIGRATION_META_KEY = "legacy_json_migrated"
SQLITE_TIMEOUT_MS = 30000
SQLITE_TIMEOUT_SECONDS = SQLITE_TIMEOUT_MS / 1000
CORRUPT_RECORD_STATUS = "corrupt"


@dataclass(frozen=True)
class TableSpec:
    """A record table: a primary key, some projected columns, and a JSON payload.

    The full record always lives in ``payload_json``. ``columns`` are the payload
    keys mirrored into real SQLite columns so they can be indexed and filtered —
    they are a query index, not the source of truth.
    """

    name: str
    primary_key: str
    columns: tuple[str, ...] = ()
    indexed: tuple[str, ...] = ()
    order_by: str = "created_at DESC"

    @property
    def all_columns(self) -> tuple[str, ...]:
        return (self.primary_key, *self.columns)

    def create_table_sql(self) -> str:
        column_ddl = ",\n                    ".join(
            f"{column} TEXT" for column in self.columns
        )
        body = f"{self.primary_key} TEXT PRIMARY KEY"
        if column_ddl:
            body += f",\n                    {column_ddl}"
        return (
            f"CREATE TABLE IF NOT EXISTS {self.name} (\n"
            f"                    {body},\n"
            "                    payload_json TEXT NOT NULL\n"
            "                );"
        )

    def create_index_sql(self) -> list[str]:
        return [
            f"CREATE INDEX IF NOT EXISTS idx_{self.name}_{column} "
            f"ON {self.name}({column});"
            for column in self.indexed
        ]


TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        name=IMPORTS_TABLE,
        primary_key="import_id",
        columns=("created_at", "status", "source_name", "data_type", "station_code"),
        indexed=("created_at",),
    ),
    TableSpec(
        name=JOBS_TABLE,
        primary_key="job_id",
        columns=(
            "created_at",
            "updated_at",
            "status",
            "model_name",
            "station_code",
            "artifact_root",
            "case_id",
            "priority",
            "queued_at",
        ),
        indexed=("created_at", "status", "case_id"),
    ),
    TableSpec(
        name=DATASETS_TABLE,
        primary_key="dataset_id",
        columns=("created_at", "updated_at", "status", "data_type", "station_code", "owner"),
        indexed=("created_at", "status", "data_type"),
    ),
    TableSpec(
        name=DATASET_VERSIONS_TABLE,
        primary_key="version_id",
        columns=(
            "dataset_id",
            "created_at",
            "version",
            "status",
            "stage",
            "quality_grade",
            "modelable",
        ),
        indexed=("dataset_id", "created_at", "status"),
    ),
    TableSpec(
        name=CASES_TABLE,
        primary_key="case_id",
        columns=("created_at", "updated_at", "status", "owner", "job_id", "station_code"),
        indexed=("created_at", "status", "owner"),
    ),
    TableSpec(
        name=MODEL_REGISTRY_TABLE,
        primary_key="model_version_id",
        columns=("created_at", "updated_at", "model_key", "version", "stage", "station_code"),
        indexed=("model_key", "stage", "created_at"),
    ),
    TableSpec(
        name=REPORTS_TABLE,
        primary_key="report_id",
        columns=("created_at", "updated_at", "status", "case_id", "owner", "format"),
        indexed=("created_at", "status", "case_id"),
    ),
    TableSpec(
        name=EVENTS_TABLE,
        primary_key="event_id",
        columns=(
            "created_at",
            "updated_at",
            "status",
            "severity",
            "case_id",
            "target_date",
            "assignee",
        ),
        indexed=("created_at", "status", "severity", "case_id"),
    ),
    TableSpec(
        name=AUDIT_EVENTS_TABLE,
        primary_key="audit_id",
        columns=("created_at", "actor", "action", "object_type", "object_id", "outcome"),
        indexed=("created_at", "actor", "action", "object_id"),
    ),
)

TABLE_SPECS_BY_NAME: dict[str, TableSpec] = {spec.name: spec for spec in TABLE_SPECS}


class SqliteStateStore:
    """Single-file SQLite store for every runtime record the software keeps.

    All tables share one shape (primary key + projected columns + JSON payload),
    so adding a domain object means adding a :class:`TableSpec`, not another set
    of hand-written upsert statements.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "app_state.sqlite3"
        self.imports_path = self.root / "data_imports.json"
        self.jobs_path = self.root / "prediction_jobs.json"
        self._initialize()
        self._migrate_legacy_json()

    # -- connection handling -------------------------------------------------

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

    # -- schema --------------------------------------------------------------

    def _initialize(self) -> None:
        with self._session(write=True) as connection:
            connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {SCHEMA_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            # Order matters on an existing database: CREATE TABLE IF NOT EXISTS
            # is a no-op for a table created by an older schema, so its new
            # columns must be added before any index can reference them.
            for spec in TABLE_SPECS:
                connection.executescript(spec.create_table_sql())
            self._ensure_columns(connection)
            for spec in TABLE_SPECS:
                for statement in spec.create_index_sql():
                    connection.execute(statement)

    def _ensure_columns(self, connection: sqlite3.Connection) -> None:
        """Add columns a :class:`TableSpec` gained since the database was created.

        SQLite has no ``ADD COLUMN IF NOT EXISTS``, so compare against
        ``PRAGMA table_info`` and add what is missing. Existing rows get NULL,
        which is correct: their payloads simply never carried that key.
        """
        for spec in TABLE_SPECS:
            existing = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({spec.name})").fetchall()
            }
            for column in spec.columns:
                if column not in existing:
                    connection.execute(f"ALTER TABLE {spec.name} ADD COLUMN {column} TEXT")

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

    # -- legacy migration ----------------------------------------------------

    def _migrate_legacy_json(self) -> None:
        if self._meta_value(LEGACY_MIGRATION_META_KEY) == "1":
            return

        for path, table in ((self.imports_path, IMPORTS_TABLE), (self.jobs_path, JOBS_TABLE)):
            spec = TABLE_SPECS_BY_NAME[table]
            for record in self._read_legacy_records(path):
                if record.get(spec.primary_key):
                    self._upsert(table, record, replace=False)

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

    # -- payload helpers -----------------------------------------------------

    def _job_updated_at(self, record: dict[str, Any]) -> str:
        return str(
            record.get("updated_at")
            or record.get("finished_at")
            or record.get("created_at")
            or ""
        )

    def _normalize(self, table: str, record: dict[str, Any]) -> dict[str, Any]:
        if table == JOBS_TABLE and "updated_at" not in record:
            return {**record, "updated_at": self._job_updated_at(record)}
        return record

    def _corrupt_record_view(
        self, *, primary_key: str, primary_value: Any, message: str
    ) -> dict[str, Any]:
        return {
            primary_key: primary_value,
            "status": CORRUPT_RECORD_STATUS,
            "message": message,
        }

    def _load_json_payload(
        self, payload_json: str, *, key: str, key_value: Any
    ) -> dict[str, Any]:
        try:
            payload = json.loads(payload_json)
        except (TypeError, JSONDecodeError) as exc:
            raise ValueError(f"Corrupt state payload for {key}={key_value}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected state payload type for {key}={key_value}.")
        return payload

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

    @staticmethod
    def _column_value(record: dict[str, Any], column: str) -> Any:
        value = record.get(column)
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)

    # -- generic CRUD --------------------------------------------------------

    def _execute_upsert(
        self,
        connection: sqlite3.Connection,
        table: str,
        record: dict[str, Any],
        *,
        replace: bool,
    ) -> None:
        spec = TABLE_SPECS_BY_NAME[table]
        normalized = self._normalize(table, record)
        columns = spec.all_columns
        placeholders = ", ".join("?" for _ in range(len(columns) + 1))
        sql = (
            f"INSERT INTO {table}({', '.join(columns)}, payload_json) "
            f"VALUES({placeholders}) "
        )
        if replace:
            assignments = ", ".join(
                f"{column} = excluded.{column}" for column in (*spec.columns, "payload_json")
            )
            sql += f"ON CONFLICT({spec.primary_key}) DO UPDATE SET {assignments}"
        else:
            sql += f"ON CONFLICT({spec.primary_key}) DO NOTHING"

        values: list[Any] = [str(normalized[spec.primary_key])]
        for column in spec.columns:
            if table == JOBS_TABLE and column == "updated_at":
                values.append(self._job_updated_at(normalized))
            elif column == "created_at":
                values.append(str(normalized.get("created_at", "")))
            else:
                values.append(self._column_value(normalized, column))
        values.append(json.dumps(normalized, ensure_ascii=False))
        connection.execute(sql, values)

    def _upsert(self, table: str, record: dict[str, Any], replace: bool) -> dict[str, Any]:
        normalized = self._normalize(table, record)
        with self._session(write=True) as connection:
            self._execute_upsert(connection, table, normalized, replace=replace)
        return normalized

    def insert(self, table: str, record: dict[str, Any]) -> dict[str, Any]:
        """Upsert ``record`` into ``table`` and return the stored payload."""
        return self._upsert(table, record, replace=True)

    def get(self, table: str, key: str) -> dict[str, Any] | None:
        spec = TABLE_SPECS_BY_NAME[table]
        with self._session() as connection:
            row = connection.execute(
                f"SELECT {spec.primary_key}, payload_json FROM {table} "
                f"WHERE {spec.primary_key} = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return self._decode_payload_row(row, spec.primary_key)

    def list(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List records, optionally filtered by equality on projected columns.

        A filter whose value is a list/tuple/set becomes an ``IN`` clause.
        """
        spec = TABLE_SPECS_BY_NAME[table]
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (filters or {}).items():
            if column not in spec.all_columns:
                raise ValueError(f"Cannot filter {table} on unprojected column '{column}'.")
            if isinstance(value, (list, tuple, set, frozenset)):
                members = [str(item) for item in value]
                if not members:
                    return []
                clauses.append(f"{column} IN ({', '.join('?' for _ in members)})")
                params.extend(members)
            else:
                clauses.append(f"{column} = ?")
                params.append(self._column_value({column: value}, column))

        sql = f"SELECT {spec.primary_key}, payload_json FROM {table}"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += f" ORDER BY {spec.order_by}"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])

        with self._session() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._decode_payload_row(row, spec.primary_key) for row in rows]

    def count(self, table: str, *, filters: dict[str, Any] | None = None) -> int:
        spec = TABLE_SPECS_BY_NAME[table]
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (filters or {}).items():
            if column not in spec.all_columns:
                raise ValueError(f"Cannot filter {table} on unprojected column '{column}'.")
            clauses.append(f"{column} = ?")
            params.append(self._column_value({column: value}, column))
        sql = f"SELECT COUNT(*) AS total FROM {table}"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        with self._session() as connection:
            row = connection.execute(sql, params).fetchone()
        return int(row["total"]) if row else 0

    def update(self, table: str, key: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge ``updates`` into the stored payload for ``key``.

        Raises ``KeyError`` when the record is absent and ``ValueError`` when the
        stored payload cannot be decoded — a corrupt row must not be silently
        overwritten with a partial update.
        """
        spec = TABLE_SPECS_BY_NAME[table]
        with self._session(write=True) as connection:
            row = connection.execute(
                f"SELECT payload_json FROM {table} WHERE {spec.primary_key} = ?",
                (key,),
            ).fetchone()
            if row is None:
                raise KeyError(key)
            current = self._load_json_payload(
                str(row["payload_json"]),
                key=spec.primary_key,
                key_value=key,
            )
            updated = {**current, **updates}
            if table == JOBS_TABLE and "updated_at" not in updates:
                updated["updated_at"] = self._job_updated_at(updated)
            self._execute_upsert(connection, table, updated, replace=True)
            return updated

    def delete(self, table: str, key: str) -> bool:
        spec = TABLE_SPECS_BY_NAME[table]
        with self._session(write=True) as connection:
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE {spec.primary_key} = ?", (key,)
            )
            return cursor.rowcount > 0

    # -- imports (kept for the existing data-import surface) -----------------

    def list_imports(self) -> list[dict[str, Any]]:
        return self.list(IMPORTS_TABLE)

    def append_import(self, record: dict[str, Any]) -> dict[str, Any]:
        return self.insert(IMPORTS_TABLE, record)

    # -- prediction jobs -----------------------------------------------------

    def list_jobs(self) -> list[dict[str, Any]]:
        return self.list(JOBS_TABLE)

    def append_job(self, record: dict[str, Any]) -> dict[str, Any]:
        return self.insert(JOBS_TABLE, record)

    def update_job(self, job_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        return self.update(JOBS_TABLE, job_id, updates)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.get(JOBS_TABLE, job_id)
