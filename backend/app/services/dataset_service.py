"""The data asset centre (review items 8, 9, 26).

A *dataset* is a named, owned stream of one data type. A *dataset version* is one
accepted (or rejected) ingestion of a file into that stream, carrying its own
quality report, canonical data file, field dictionary and lineage.

This service replaces the two overlapping ingestion entry points the review
flagged — browser upload and server-path import — with one flow that always runs
the acceptance chain, so "uploaded" can never again be mistaken for "usable".
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

import pandas as pd

from backend.app.config import Settings
from backend.app.domain.codes import (
    MODELABLE_GRADES,
    DatasetStatus,
    ErrorCode,
    IngestionStage,
    QualityGrade,
)
from backend.app.services.ingestion import (
    CANONICAL_DATA_FILENAME,
    FIELD_DICTIONARY_FILENAME,
    LINEAGE_FILENAME,
    QUALITY_REPORT_FILENAME,
    SUPPORTED_DATA_TYPES,
    SUPPORTED_SUFFIXES,
    field_dictionary,
    persist_result,
    run_ingestion,
)
from backend.app.services.ingestion.schema_registry import normalize_column
from backend.app.services.state_store import (
    DATASET_VERSIONS_TABLE,
    DATASETS_TABLE,
    SqliteStateStore,
)
from backend.app.services.upload_guard import (
    UploadRejected,
    copy_managed_file,
    resolve_managed_path,
    safe_filename,
    store_upload,
)

ID_LENGTH = 12
PREVIEW_DEFAULT_LIMIT = 50
PREVIEW_MAX_LIMIT = 500


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return uuid4().hex[:ID_LENGTH]


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, so a version's provenance can be re-verified.

    Review item 8/26: a dataset version must carry a content hash so the answer
    to "has this file changed since it was ingested?" is not a guess.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DatasetNotFound(KeyError):
    pass


class DatasetService:
    def __init__(self, settings: Settings, store: SqliteStateStore) -> None:
        self.settings = settings
        self.store = store
        self.settings.datasets_root.mkdir(parents=True, exist_ok=True)
        self.settings.imports_root.mkdir(parents=True, exist_ok=True)
        self.settings.managed_import_root.mkdir(parents=True, exist_ok=True)

    # -- paths ---------------------------------------------------------------

    def _version_root(self, dataset_id: str, version: int) -> Path:
        return self.settings.datasets_root / dataset_id / f"v{version}"

    def _raw_path(self, dataset_id: str, version: int, filename: str) -> Path:
        return self._version_root(dataset_id, version) / "raw" / filename

    # -- ingestion entry points ---------------------------------------------

    def ingest_upload(
        self,
        *,
        source: BinaryIO,
        filename: str | None,
        data_type: str,
        station_code: str | None,
        owner: str,
        dataset_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Accept a browser upload and run it through the full acceptance chain."""
        self._assert_supported_type(data_type)
        dataset = self._resolve_or_create_dataset(
            dataset_id=dataset_id,
            data_type=data_type,
            station_code=station_code,
            owner=owner,
            title=title,
            source_kind="upload",
        )
        version = self._next_version(str(dataset["dataset_id"]))
        name = safe_filename(filename)
        stored = store_upload(
            source=source,
            filename=name,
            target_path=self._raw_path(str(dataset["dataset_id"]), version, name),
            allowed_suffixes=SUPPORTED_SUFFIXES,
            max_bytes=self.settings.max_upload_bytes,
            max_compression_ratio=self.settings.max_compression_ratio,
        )
        return self._ingest_stored_file(
            dataset=dataset,
            version=version,
            stored_path=stored.path,
            source_name=stored.filename,
            source_kind="upload",
            size_bytes=stored.size_bytes,
            owner=owner,
        )

    def ingest_managed_path(
        self,
        *,
        relative_path: str,
        data_type: str,
        station_code: str | None,
        owner: str,
        dataset_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Import a file from the controlled inbox directory.

        The old endpoint accepted any absolute server path; this one resolves
        strictly inside ``settings.managed_import_root``.
        """
        self._assert_supported_type(data_type)
        source = resolve_managed_path(relative_path, self.settings.managed_import_root)
        dataset = self._resolve_or_create_dataset(
            dataset_id=dataset_id,
            data_type=data_type,
            station_code=station_code,
            owner=owner,
            title=title,
            source_kind="managed_path",
        )
        version = self._next_version(str(dataset["dataset_id"]))
        stored = copy_managed_file(
            source=source,
            target_path=self._raw_path(str(dataset["dataset_id"]), version, source.name),
            allowed_suffixes=SUPPORTED_SUFFIXES,
            max_bytes=self.settings.max_upload_bytes,
            max_compression_ratio=self.settings.max_compression_ratio,
        )
        return self._ingest_stored_file(
            dataset=dataset,
            version=version,
            stored_path=stored.path,
            source_name=stored.filename,
            source_kind="managed_path",
            size_bytes=stored.size_bytes,
            owner=owner,
        )

    def ingest_source_path(
        self,
        *,
        source_path: Path,
        data_type: str,
        station_code: str | None,
        owner: str,
        dataset_id: str | None = None,
        title: str | None = None,
        kind: str = "fact_source",
        notes: list[str] | None = None,
        proxy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Import a baseline file already committed under the repository data tree.

        This is the entry point the registration bootstrap uses to bring the
        pre-existing ``data/`` files into the dataset/version chain. Unlike
        ``ingest_managed_path`` it is not restricted to the inbox: the caller is
        an operator running a trusted local script, and the source must already
        resolve to a file.
        """
        self._assert_supported_type(data_type)
        source = Path(source_path).resolve()
        if not source.is_file():
            raise UploadRejected(ErrorCode.NOT_FOUND, f"Source file does not exist: {source}")
        dataset = self._resolve_or_create_dataset(
            dataset_id=dataset_id,
            data_type=data_type,
            station_code=station_code,
            owner=owner,
            title=title,
            source_kind="baseline",
            kind=kind,
            notes=notes,
            proxy=proxy,
        )
        version = self._next_version(str(dataset["dataset_id"]))
        stored = copy_managed_file(
            source=source,
            target_path=self._raw_path(str(dataset["dataset_id"]), version, source.name),
            allowed_suffixes=SUPPORTED_SUFFIXES,
            max_bytes=self.settings.max_upload_bytes,
            max_compression_ratio=self.settings.max_compression_ratio,
        )
        return self._ingest_stored_file(
            dataset=dataset,
            version=version,
            stored_path=stored.path,
            source_name=stored.filename,
            source_kind="baseline",
            size_bytes=stored.size_bytes,
            owner=owner,
            kind=kind,
            notes=notes,
            proxy=proxy,
        )

    def _ingest_stored_file(
        self,
        *,
        dataset: dict[str, Any],
        version: int,
        stored_path: Path,
        source_name: str,
        source_kind: str,
        size_bytes: int,
        owner: str,
        kind: str = "fact_source",
        notes: list[str] | None = None,
        proxy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dataset_id = str(dataset["dataset_id"])
        data_type = str(dataset["data_type"])
        version_root = self._version_root(dataset_id, version)

        # Review item 9: quality assessment is not an optional extra step the
        # user has to remember to trigger — it runs as part of every import.
        result = run_ingestion(stored_path, data_type)

        lineage = {
            "dataset_id": dataset_id,
            "version": version,
            "source_name": source_name,
            "source_kind": source_kind,
            "raw_path": str(stored_path),
            "source_sha256": sha256_file(stored_path),
            "ingested_at": utc_now(),
            "ingested_by": owner,
            "kind": kind,
            "notes": list(notes or []),
            "proxy": dict(proxy or {}),
            "used_by_cases": [],
        }
        artifacts = persist_result(result, version_root, lineage)

        quality = result.quality
        record = {
            "version_id": f"{dataset_id}-v{version}",
            "dataset_id": dataset_id,
            "version": str(version),
            "created_at": utc_now(),
            "created_by": owner,
            "data_type": data_type,
            "source_name": source_name,
            "source_kind": source_kind,
            "source_sha256": lineage["source_sha256"],
            "raw_path": str(stored_path),
            "size_bytes": size_bytes,
            "kind": kind,
            "notes": list(notes or []),
            "proxy": dict(proxy or {}),
            "status": str(
                DatasetStatus.ACCEPTED if result.accepted else DatasetStatus.REJECTED
            ),
            "stage": str(result.final_stage),
            "blocked_at": str(result.blocked_at) if result.blocked_at else None,
            "quality_grade": str(quality.grade),
            "modelable": "1" if quality.modelable else "0",
            "modelable_rows": quality.modelable_rows,
            "aligned_rows": quality.aligned_rows,
            "source_rows": quality.source_rows,
            "missing_rate": quality.missing_rate,
            "duplicate_rows": quality.duplicate_rows,
            "coverage_start": quality.time_coverage_start,
            "coverage_end": quality.time_coverage_end,
            "station_coverage": quality.station_coverage,
            "blocking_reasons": quality.blocking_reasons,
            "artifacts": artifacts,
            "stages": [item.as_dict() for item in result.stages],
            "used_by_cases": [],
        }
        self.store.insert(DATASET_VERSIONS_TABLE, record)
        self._refresh_dataset_rollup(dataset_id)
        return record

    # -- dataset bookkeeping -------------------------------------------------

    def _assert_supported_type(self, data_type: str) -> None:
        if str(data_type).strip() not in SUPPORTED_DATA_TYPES:
            raise UploadRejected(
                ErrorCode.VALIDATION_FAILED,
                f"Unsupported data_type '{data_type}'. "
                f"Supported: {sorted(SUPPORTED_DATA_TYPES)}.",
            )

    def _resolve_or_create_dataset(
        self,
        *,
        dataset_id: str | None,
        data_type: str,
        station_code: str | None,
        owner: str,
        title: str | None,
        source_kind: str,
        kind: str = "fact_source",
        notes: list[str] | None = None,
        proxy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if dataset_id:
            existing = self.store.get(DATASETS_TABLE, dataset_id)
            if existing is None:
                raise DatasetNotFound(dataset_id)
            if existing.get("data_type") != data_type:
                raise UploadRejected(
                    ErrorCode.VALIDATION_FAILED,
                    f"Dataset {dataset_id} holds '{existing.get('data_type')}' data, "
                    f"not '{data_type}'.",
                )
            return existing

        new_id = _new_id()
        record = {
            "dataset_id": new_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "title": title or f"{data_type}-{new_id}",
            "data_type": data_type,
            "station_code": station_code,
            "owner": owner,
            "status": str(DatasetStatus.PROCESSING),
            "source_kind": source_kind,
            "kind": kind,
            "notes": list(notes or []),
            "proxy": dict(proxy or {}),
            "version_count": 0,
            "latest_version": None,
        }
        return self.store.insert(DATASETS_TABLE, record)

    def ensure_dataset(
        self,
        *,
        dataset_id: str,
        data_type: str,
        station_code: str | None,
        owner: str,
        title: str | None = None,
        kind: str = "fact_source",
        notes: list[str] | None = None,
        proxy: dict[str, Any] | None = None,
        source_kind: str = "baseline",
    ) -> dict[str, Any]:
        """Create a dataset under a fixed id, or return the existing one.

        The registration bootstrap uses this so dataset ids are stable across
        runs (``wq_wusongkou``, ``weather_shanghai``, …) rather than random, so
        the committed registration table can name them.
        """
        existing = self.store.get(DATASETS_TABLE, dataset_id)
        if existing is not None:
            return existing
        record = {
            "dataset_id": dataset_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "title": title or f"{data_type}-{dataset_id}",
            "data_type": data_type,
            "station_code": station_code,
            "owner": owner,
            "status": str(DatasetStatus.PROCESSING),
            "source_kind": source_kind,
            "kind": kind,
            "notes": list(notes or []),
            "proxy": dict(proxy or {}),
            "version_count": 0,
            "latest_version": None,
        }
        return self.store.insert(DATASETS_TABLE, record)

    def has_version_with_sha(self, dataset_id: str, sha256: str) -> bool:
        """True when the dataset already ingested a version with this content hash.

        Lets the bootstrap re-run without creating duplicate versions (review
        item 8: re-importing the same file must not create duplicate facts).
        """
        return any(
            version.get("source_sha256") == sha256
            for version in self.list_versions(dataset_id)
        )

    def _next_version(self, dataset_id: str) -> int:
        versions = self.store.list(DATASET_VERSIONS_TABLE, filters={"dataset_id": dataset_id})
        return len(versions) + 1

    def _refresh_dataset_rollup(self, dataset_id: str) -> dict[str, Any]:
        """Recompute the dataset-level summary shown in the asset centre."""
        versions = self.list_versions(dataset_id)
        latest = versions[0] if versions else None
        accepted = [
            item for item in versions if item.get("status") == str(DatasetStatus.ACCEPTED)
        ]
        latest_accepted = accepted[0] if accepted else None

        updates: dict[str, Any] = {
            "updated_at": utc_now(),
            "version_count": len(versions),
            "latest_version": latest.get("version") if latest else None,
            "latest_version_id": latest.get("version_id") if latest else None,
            "latest_accepted_version_id": (
                latest_accepted.get("version_id") if latest_accepted else None
            ),
            # The single effective version a reader should consume. Accepted is
            # preferred; a dataset with only rejected versions has no effective
            # data, so this stays null rather than pointing at a broken version.
            "current_version_id": (
                latest_accepted.get("version_id") if latest_accepted else None
            ),
            "quality_grade": (
                latest_accepted.get("quality_grade")
                if latest_accepted
                else (latest.get("quality_grade") if latest else None)
            ),
            "modelable": "1" if latest_accepted else "0",
            "coverage_start": latest_accepted.get("coverage_start") if latest_accepted else None,
            "coverage_end": latest_accepted.get("coverage_end") if latest_accepted else None,
            "station_coverage": (
                latest_accepted.get("station_coverage", []) if latest_accepted else []
            ),
            "modelable_rows": (
                latest_accepted.get("modelable_rows", 0) if latest_accepted else 0
            ),
        }
        current = self.store.get(DATASETS_TABLE, dataset_id) or {}
        if current.get("status") != str(DatasetStatus.ARCHIVED):
            updates["status"] = str(
                DatasetStatus.ACCEPTED if latest_accepted else DatasetStatus.REJECTED
            )
        return self.store.update(DATASETS_TABLE, dataset_id, updates)

    def register_derived_file(
        self,
        *,
        source_path: Path,
        data_type: str,
        station_code: str | None,
        owner: str,
        dataset_id: str | None = None,
        title: str | None = None,
        kind: str = "derived",
        notes: list[str] | None = None,
        proxy: dict[str, Any] | None = None,
        source_version_id: str | None = None,
    ) -> dict[str, Any]:
        """Register an already-standardized file as a dataset version.

        Used for derived/fusion/proxy/static-reference files that are not raw
        fact inputs to the modelling chain, so they should not be forced through
        field mapping. It still produces the same artifacts — a canonical copy,
        a quality report, a field dictionary, lineage and a content hash — so the
        asset centre treats every file the same way (review item 8).
        """
        source = Path(source_path).resolve()
        if not source.is_file():
            raise UploadRejected(ErrorCode.NOT_FOUND, f"Source file does not exist: {source}")

        dataset = self._resolve_or_create_dataset(
            dataset_id=dataset_id,
            data_type=str(data_type).strip(),
            station_code=station_code,
            owner=owner,
            title=title,
            source_kind="baseline",
            kind=kind,
            notes=notes,
            proxy=proxy,
        )
        dataset_id = str(dataset["dataset_id"])
        version = self._next_version(dataset_id)
        version_root = self._version_root(dataset_id, version)

        stored = copy_managed_file(
            source=source,
            target_path=self._raw_path(dataset_id, version, source.name),
            allowed_suffixes=SUPPORTED_SUFFIXES,
            max_bytes=self.settings.max_upload_bytes,
            max_compression_ratio=self.settings.max_compression_ratio,
        )

        frame = self._read_tabular(stored.path)
        summary = self._summarize_frame(frame, data_type=str(data_type).strip())

        lineage = {
            "dataset_id": dataset_id,
            "version": version,
            "source_name": stored.filename,
            "source_kind": "baseline",
            "raw_path": str(stored.path),
            "source_sha256": sha256_file(stored.path),
            "ingested_at": utc_now(),
            "ingested_by": owner,
            "kind": kind,
            "notes": list(notes or []),
            "proxy": dict(proxy or {}),
            "source_version_id": source_version_id,
            "used_by_cases": [],
        }

        version_root.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, str] = {}
        if frame is not None and not frame.empty:
            data_path = version_root / CANONICAL_DATA_FILENAME
            frame.to_csv(data_path, index=False, encoding="utf-8-sig")
            artifacts["data"] = str(data_path)

        quality_report = {
            "data_type": summary["data_type"],
            "kind": kind,
            "source_name": stored.filename,
            "source_sha256": lineage["source_sha256"],
            "rows": summary["rows"],
            "columns": summary["columns"],
            "missing_rates": summary["missing_rates"],
            "coverage_start": summary["coverage_start"],
            "coverage_end": summary["coverage_end"],
            "stations": summary["stations"],
            "notes": list(notes or []),
            "proxy": dict(proxy or {}),
            "grade": summary["grade"],
            "modelable": kind == "fact_source",
        }
        quality_path = version_root / QUALITY_REPORT_FILENAME
        quality_path.write_text(
            json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        artifacts["quality_report"] = str(quality_path)

        dictionary_path = version_root / FIELD_DICTIONARY_FILENAME
        dictionary_path.write_text(
            json.dumps(
                {"data_type": summary["data_type"], "fields": summary["field_dictionary"]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        artifacts["field_dictionary"] = str(dictionary_path)

        lineage_path = version_root / LINEAGE_FILENAME
        lineage_path.write_text(
            json.dumps(lineage, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        artifacts["lineage"] = str(lineage_path)

        record = {
            "version_id": f"{dataset_id}-v{version}",
            "dataset_id": dataset_id,
            "version": str(version),
            "created_at": utc_now(),
            "created_by": owner,
            "data_type": str(data_type).strip(),
            "source_name": stored.filename,
            "source_kind": "baseline",
            "source_sha256": lineage["source_sha256"],
            "raw_path": str(stored.path),
            "size_bytes": stored.size_bytes,
            "kind": kind,
            "notes": list(notes or []),
            "proxy": dict(proxy or {}),
            "source_version_id": source_version_id,
            "status": str(DatasetStatus.ACCEPTED),
            "stage": str(IngestionStage.ACCEPTED),
            "blocked_at": None,
            "quality_grade": summary["grade"],
            "modelable": "1" if kind == "fact_source" else "0",
            "modelable_rows": summary["rows"] if kind == "fact_source" else 0,
            "aligned_rows": summary["rows"],
            "source_rows": summary["rows"],
            "missing_rate": summary["missing_rate"],
            "duplicate_rows": 0,
            "coverage_start": summary["coverage_start"],
            "coverage_end": summary["coverage_end"],
            "station_coverage": summary["stations"],
            "blocking_reasons": [],
            "artifacts": artifacts,
            "stages": [],
            "used_by_cases": [],
        }
        self.store.insert(DATASET_VERSIONS_TABLE, record)
        self._refresh_dataset_rollup(dataset_id)
        return record

    def _read_tabular(self, path: Path) -> pd.DataFrame | None:
        suffix = path.suffix.lower()
        try:
            if suffix == ".csv":
                return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
            if suffix in {".xls", ".xlsx"}:
                return pd.read_excel(path, dtype=str).fillna("")
            if suffix == ".parquet":
                return pd.read_parquet(path).astype(str)
            if suffix == ".json":
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                records = payload.get("records", payload) if isinstance(payload, dict) else payload
                if isinstance(records, list):
                    return pd.DataFrame(records).astype(str)
        except Exception:
            return None
        return None

    def _summarize_frame(self, frame: pd.DataFrame | None, data_type: str) -> dict[str, Any]:
        if frame is None or frame.empty:
            return {
                "data_type": data_type,
                "rows": 0,
                "columns": [],
                "missing_rates": {},
                "missing_rate": 0.0,
                "coverage_start": None,
                "coverage_end": None,
                "stations": [],
                "grade": str(QualityGrade.D),
                "field_dictionary": [],
            }

        rows = int(len(frame))
        columns = [str(column) for column in frame.columns]
        blank = frame.replace({"": None, "nan": None})
        missing_rates = {
            str(column): round(float(blank[column].isna().mean()), 6)
            for column in frame.columns
        }
        # DataFrame.isna().mean() returns a per-column Series; collapse it to a
        # single overall cell-missing rate.
        missing_rate = float(blank.isna().to_numpy().mean()) if rows else 0.0

        coverage_start = coverage_end = None
        stations: list[str] = []
        normalized_columns = {str(c): normalize_column(str(c)) for c in frame.columns}
        # Primary date columns: a single per-row timestamp. Derived files use
        # ``sample_date``; the raw fact files use ``date`` / ``监测时间``.
        date_candidates = {
            "date",
            "datetime",
            "时间",
            "日期",
            "sample_date",
            "监测时间",
            "采样日期",
        }
        for column, normalized in normalized_columns.items():
            if normalized in date_candidates:
                parsed = pd.to_datetime(frame[column], errors="coerce")
                if parsed.notna().any():
                    coverage_start = parsed.min().date().isoformat()
                    coverage_end = parsed.max().date().isoformat()
            if normalized in {"station_code", "站点", "站点编码"}:
                stations = sorted(
                    frame[column].dropna().astype(str).unique().tolist()
                )
        # Fallback: reference tables that only carry a validity interval, e.g.
        # the station catalog's start_date/end_date.
        if coverage_start is None:
            start_col = next(
                (c for c, n in normalized_columns.items() if n == "start_date"), None
            )
            end_col = next(
                (c for c, n in normalized_columns.items() if n == "end_date"), None
            )
            if start_col is not None:
                starts = pd.to_datetime(frame[start_col], errors="coerce")
                if starts.notna().any():
                    coverage_start = starts.min().date().isoformat()
            if end_col is not None:
                ends = pd.to_datetime(frame[end_col], errors="coerce")
                if ends.notna().any():
                    coverage_end = ends.max().date().isoformat()

        field_dictionary = [
            {
                "column": str(column),
                "dtype": str(frame[column].dtype),
                "missing_rate": missing_rates.get(str(column), 0.0),
            }
            for column in frame.columns
        ]

        grade = QualityGrade.A if missing_rate <= 0.05 else (
            QualityGrade.B if missing_rate <= 0.20 else QualityGrade.C
        )
        return {
            "data_type": data_type,
            "rows": rows,
            "columns": columns,
            "missing_rates": missing_rates,
            "missing_rate": missing_rate,
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
            "stations": stations,
            "grade": str(grade),
            "field_dictionary": field_dictionary,
        }

    # -- queries -------------------------------------------------------------

    def list_datasets(
        self,
        *,
        data_type: str | None = None,
        status: str | None = None,
        owner: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if data_type:
            filters["data_type"] = data_type
        if status:
            filters["status"] = status
        if owner:
            filters["owner"] = owner
        return self.store.list(DATASETS_TABLE, filters=filters or None)

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        record = self.store.get(DATASETS_TABLE, dataset_id)
        if record is None:
            raise DatasetNotFound(dataset_id)
        return record

    def list_versions(self, dataset_id: str) -> list[dict[str, Any]]:
        versions = self.store.list(DATASET_VERSIONS_TABLE, filters={"dataset_id": dataset_id})
        return sorted(
            versions,
            key=lambda item: int(str(item.get("version", 0)) or 0),
            reverse=True,
        )

    def get_version(self, version_id: str) -> dict[str, Any]:
        record = self.store.get(DATASET_VERSIONS_TABLE, version_id)
        if record is None:
            raise DatasetNotFound(version_id)
        return record

    def quality_report(self, version_id: str) -> dict[str, Any]:
        """Full stage-by-stage report, read back from the persisted artifact."""
        import json

        version = self.get_version(version_id)
        path = (version.get("artifacts") or {}).get("quality_report")
        if not path or not Path(str(path)).exists():
            raise DatasetNotFound(f"{version_id}:{QUALITY_REPORT_FILENAME}")
        return json.loads(Path(str(path)).read_text(encoding="utf-8"))

    def preview(self, version_id: str, limit: int = PREVIEW_DEFAULT_LIMIT) -> dict[str, Any]:
        """First rows of the canonicalized data — what the model would actually see."""
        version = self.get_version(version_id)
        path = (version.get("artifacts") or {}).get("data")
        capped = max(1, min(int(limit), PREVIEW_MAX_LIMIT))
        if not path or not Path(str(path)).exists():
            return {
                "version_id": version_id,
                "columns": [],
                "rows": [],
                "available": False,
                "reason": version.get("blocked_at") or "no_accepted_data",
            }
        frame = pd.read_csv(Path(str(path)), encoding="utf-8-sig", nrows=capped)
        frame = frame.where(pd.notna(frame), None)
        return {
            "version_id": version_id,
            "columns": [str(column) for column in frame.columns],
            "rows": frame.to_dict(orient="records"),
            "available": True,
            "total_rows": version.get("aligned_rows", 0),
        }

    def field_dictionary(self, data_type: str) -> dict[str, Any]:
        self._assert_supported_type(data_type)
        return field_dictionary(data_type)

    def lineage(self, version_id: str) -> dict[str, Any]:
        """Where this version came from and which cases consumed it."""
        version = self.get_version(version_id)
        return {
            "version_id": version_id,
            "dataset_id": version.get("dataset_id"),
            "source_name": version.get("source_name"),
            "source_kind": version.get("source_kind"),
            "source_sha256": version.get("source_sha256"),
            "raw_path": version.get("raw_path"),
            "created_at": version.get("created_at"),
            "created_by": version.get("created_by"),
            "stage": version.get("stage"),
            "status": version.get("status"),
            "kind": version.get("kind", "fact_source"),
            "notes": version.get("notes", []),
            "proxy": version.get("proxy", {}),
            "used_by_cases": version.get("used_by_cases", []),
        }

    def get_current_version(self, dataset_id: str) -> dict[str, Any]:
        """The single effective version a reader should consume.

        Prefers the latest accepted version; if the dataset has none (e.g. every
        version was rejected), raises ``DatasetNotFound`` so a reader fails
        loudly instead of silently falling back to an unregistered raw file.
        """
        dataset = self.get_dataset(dataset_id)
        current_id = dataset.get("current_version_id")
        if not current_id:
            raise DatasetNotFound(f"{dataset_id}:no_accepted_version")
        return self.get_version(str(current_id))

    def resolve_reading_path(self, dataset_id: str, *, raw: bool = False) -> Path:
        """Filesystem path a reader should consume for the current version.

        ``raw=True`` returns the byte-for-byte copy of the ingested source;
        the default returns the canonicalized ``data.csv``.
        """
        version = self.get_current_version(dataset_id)
        if raw:
            return Path(str(version["raw_path"]))
        data_path = (version.get("artifacts") or {}).get("data")
        if not data_path or not Path(str(data_path)).exists():
            raise DatasetNotFound(f"{version['version_id']}:no_canonical_data")
        return Path(str(data_path))

    # -- the modelling gate --------------------------------------------------

    def modelable_versions(
        self, *, data_type: str | None = None, station_code: str | None = None
    ) -> list[dict[str, Any]]:
        """Versions a prediction case is allowed to consume.

        Review item 9: *禁止直接对未经质量校验的数据执行正式预测*.
        """
        candidates = self.store.list(
            DATASET_VERSIONS_TABLE, filters={"status": str(DatasetStatus.ACCEPTED)}
        )
        results = []
        for version in candidates:
            if version.get("modelable") not in ("1", 1, True):
                continue
            if data_type and version.get("data_type") != data_type:
                continue
            if station_code:
                coverage = version.get("station_coverage") or []
                if coverage and station_code not in coverage:
                    continue
            results.append(version)
        return results

    def assert_modelable(self, version_id: str) -> dict[str, Any]:
        """Raise unless this version passed the quality gate."""
        version = self.get_version(version_id)
        grade = QualityGrade(str(version.get("quality_grade", QualityGrade.D)))
        if version.get("status") != str(DatasetStatus.ACCEPTED) or grade not in MODELABLE_GRADES:
            raise UploadRejected(
                ErrorCode.DATASET_NOT_MODELABLE,
                f"Dataset version {version_id} is {version.get('status')} "
                f"(grade {grade}, blocked at {version.get('blocked_at')}); "
                "it cannot be used for a prediction run.",
            )
        return version

    def coverage_window(self, version_ids: list[str]) -> tuple[str | None, str | None]:
        """Intersection of the date coverage of several versions.

        Used to reject a requested date range at submit time rather than after
        the pipeline has run (review item 1).
        """
        starts: list[str] = []
        ends: list[str] = []
        for version_id in version_ids:
            version = self.get_version(version_id)
            if version.get("coverage_start"):
                starts.append(str(version["coverage_start"]))
            if version.get("coverage_end"):
                ends.append(str(version["coverage_end"]))
        return (max(starts) if starts else None, min(ends) if ends else None)

    def record_case_usage(self, version_ids: list[str], case_id: str) -> None:
        """Append ``case_id`` to each version's lineage (review item 8: 数据血缘)."""
        for version_id in version_ids:
            try:
                version = self.get_version(version_id)
            except DatasetNotFound:
                continue
            used = list(version.get("used_by_cases") or [])
            if case_id not in used:
                used.append(case_id)
                self.store.update(
                    DATASET_VERSIONS_TABLE, version_id, {"used_by_cases": used}
                )

    # -- lifecycle -----------------------------------------------------------

    def archive_dataset(self, dataset_id: str, actor: str) -> dict[str, Any]:
        self.get_dataset(dataset_id)
        return self.store.update(
            DATASETS_TABLE,
            dataset_id,
            {
                "status": str(DatasetStatus.ARCHIVED),
                "updated_at": utc_now(),
                "archived_by": actor,
            },
        )

    def delete_dataset(self, dataset_id: str, actor: str) -> dict[str, Any]:
        """Delete a dataset and every stored byte of its versions.

        Refuses while any case still references a version, so a deletion can
        never orphan a case's inputs.
        """
        self.get_dataset(dataset_id)
        versions = self.list_versions(dataset_id)
        blocking = {
            str(version["version_id"]): version.get("used_by_cases") or []
            for version in versions
            if version.get("used_by_cases")
        }
        if blocking:
            raise UploadRejected(
                ErrorCode.INVALID_STATE_TRANSITION,
                f"Dataset {dataset_id} is still used by cases: {blocking}.",
            )

        root = self.settings.datasets_root / dataset_id
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        for version in versions:
            self.store.delete(DATASET_VERSIONS_TABLE, str(version["version_id"]))
        self.store.update(
            DATASETS_TABLE,
            dataset_id,
            {
                "status": str(DatasetStatus.DELETED),
                "updated_at": utc_now(),
                "deleted_by": actor,
            },
        )
        self.store.delete(DATASETS_TABLE, dataset_id)
        return {"dataset_id": dataset_id, "deleted_versions": len(versions)}

    def purge_expired(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Delete rejected versions past the upload retention window (item 26)."""
        retention_days = self.settings.upload_retention_days
        if retention_days <= 0:
            return {"scanned": 0, "purged": 0, "retention_days": retention_days}

        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
        purged = 0
        rejected = self.store.list(
            DATASET_VERSIONS_TABLE, filters={"status": str(DatasetStatus.REJECTED)}
        )
        for version in rejected:
            created_at = str(version.get("created_at") or "")
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if created >= cutoff or version.get("used_by_cases"):
                continue
            root = Path(
                str(
                    (version.get("artifacts") or {}).get("quality_report", "")
                )
            ).parent
            if root.exists() and self.settings.datasets_root in root.resolve().parents:
                shutil.rmtree(root, ignore_errors=True)
            self.store.delete(DATASET_VERSIONS_TABLE, str(version["version_id"]))
            purged += 1

        return {"scanned": len(rejected), "purged": purged, "retention_days": retention_days}

    # -- summary for the home page ------------------------------------------

    def freshness_summary(self) -> dict[str, Any]:
        """Data-freshness signal for the operational home page (review item 12)."""
        datasets = self.list_datasets()
        accepted = [d for d in datasets if d.get("status") == str(DatasetStatus.ACCEPTED)]
        coverage_ends = [
            str(d["coverage_end"]) for d in accepted if d.get("coverage_end")
        ]
        latest_coverage = max(coverage_ends) if coverage_ends else None
        stale_days: int | None = None
        if latest_coverage:
            try:
                latest = datetime.fromisoformat(latest_coverage).replace(tzinfo=timezone.utc)
                stale_days = (datetime.now(timezone.utc) - latest).days
            except ValueError:
                stale_days = None

        return {
            "dataset_count": len(datasets),
            "accepted_count": len(accepted),
            "rejected_count": sum(
                1 for d in datasets if d.get("status") == str(DatasetStatus.REJECTED)
            ),
            "modelable_count": sum(1 for d in accepted if d.get("modelable") in ("1", 1, True)),
            "latest_coverage_end": latest_coverage,
            "stale_days": stale_days,
            "is_stale": (
                stale_days is not None
                and stale_days > self.settings.data_freshness_warning_days
            ),
            "warning_threshold_days": self.settings.data_freshness_warning_days,
        }

    def quality_alerts(self, limit: int = 10) -> list[dict[str, Any]]:
        """Recently rejected versions, for the home page's 数据质量异常 panel."""
        rejected = self.store.list(
            DATASET_VERSIONS_TABLE,
            filters={"status": str(DatasetStatus.REJECTED)},
            limit=limit,
        )
        return [
            {
                "version_id": item.get("version_id"),
                "dataset_id": item.get("dataset_id"),
                "data_type": item.get("data_type"),
                "source_name": item.get("source_name"),
                "created_at": item.get("created_at"),
                "blocked_at": item.get("blocked_at"),
                "quality_grade": item.get("quality_grade"),
                "blocking_reasons": item.get("blocking_reasons", []),
            }
            for item in rejected
        ]
