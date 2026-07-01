from __future__ import annotations

import copy
import ctypes
import json
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import yaml
from fastapi import UploadFile

from backend.app.config import Settings
from backend.app.schemas import DataImportRequest, PredictionJobCreateRequest
from backend.app.services.artifact_repository import ArtifactRepository
from backend.app.services.state_store import SqliteStateStore

JOB_ID_LENGTH = 12
LOG_PREVIEW_LINE_COUNT = 20
RUNNING_STATUS = "running"
COMPLETED_STATUS = "completed"
FAILED_STATUS = "failed"
ORPHANED_STATUS = "orphaned"
TERMINAL_STATUSES = {COMPLETED_STATUS, FAILED_STATUS, ORPHANED_STATUS}
DEFAULT_IMPORT_FAILURE_MESSAGE = "Source file does not exist."
EXISTING_ARTIFACT_MESSAGE = "Snapshot created from currently integrated runtime artifacts."
LAUNCHED_MESSAGE = "Pipeline launched in job-scoped runtime directory."
DETACHED_WAIT_MESSAGE = "Job is still running in detached mode; waiting for status file completion."
COMPLETED_MESSAGE = "Job completed with verified job-scoped artifacts."
ORPHANED_MESSAGE = "Job process is no longer alive and no completion marker was found."
ARTIFACT_VALIDATION_FAILURE_MESSAGE = (
    "Job reported completion but required artifacts were missing or unreadable."
)
JOB_RUNNER_MODULE = "backend.app.tasks.job_runner"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HYDRODYNAMICS_OUTPUT_DIR_NAME = "hydrodynamics_preprocessed"
HYDRODYNAMICS_WIDE_FILENAME = "shanghai_hydrodynamics_daily_wide.csv"
NDTI_OUTPUT_DIR_NAME = "ndti_preprocessed"
ACTIVE_PROCESS_EXIT_CODE = 259
IMPORTED_STATUS = "imported"
IMPORT_COPY_FAILURE_PREFIX = "Copy failed: "
SUPPORTED_IMPORT_TYPES = {
    "water_quality",
    "weather",
    "hydrodynamics",
    "water_control",
    "boundary_labels",
    "spatial",
}
SUPPORTED_UPLOAD_SUFFIXES = {".csv", ".xls", ".xlsx", ".json"}


@dataclass(frozen=True)
class JobRuntimePaths:
    run_root: Path
    output_root: Path
    status_file: Path
    stdout_log: Path
    stderr_log: Path

    @classmethod
    def build(cls, job_runs_root: Path, job_id: str) -> "JobRuntimePaths":
        run_root = job_runs_root / job_id
        return cls(
            run_root=run_root,
            output_root=run_root / "outputs",
            status_file=run_root / "run_status.json",
            stdout_log=run_root / "logs" / "stdout.log",
            stderr_log=run_root / "logs" / "stderr.log",
        )



def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RuntimeJobService:
    TERMINAL_STATUSES = TERMINAL_STATUSES

    def __init__(
        self,
        settings: Settings,
        repository: ArtifactRepository,
        store: SqliteStateStore,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.store = store
        self._processes: dict[str, subprocess.Popen[Any]] = {}
        self._process_lock = threading.Lock()
        self.settings.imports_root.mkdir(parents=True, exist_ok=True)
        self.settings.job_logs_root.mkdir(parents=True, exist_ok=True)
        self.settings.job_runs_root.mkdir(parents=True, exist_ok=True)

    def import_data(self, payload: DataImportRequest) -> dict[str, Any]:
        source = Path(payload.file_path).expanduser()
        record = self._build_import_record(payload, source)
        if not source.exists() or not source.is_file():
            return self._append_import_failure(record, DEFAULT_IMPORT_FAILURE_MESSAGE)

        target_path = self._import_target_path(payload.data_type, record["import_id"], source.name)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target_path)
        except OSError as exc:
            return self._append_import_failure(
                record,
                f"{IMPORT_COPY_FAILURE_PREFIX}{exc}",
            )

        finalized_record = {
            **record,
            "status": IMPORTED_STATUS,
            "stored_path": str(target_path),
            "file_size_bytes": target_path.stat().st_size,
        }
        rows_detected = self._detect_rows(target_path)
        if rows_detected is not None:
            finalized_record["rows_detected"] = rows_detected
        return self.store.append_import(finalized_record)

    def list_imports(self) -> list[dict[str, Any]]:
        return sorted(
            self.store.list_imports(),
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )

    def upload_data_files(
        self,
        *,
        data_type: str,
        station_code: str,
        time_granularity: str,
        files: list[UploadFile],
    ) -> dict[str, Any]:
        normalized_type = str(data_type or "").strip()
        if normalized_type not in SUPPORTED_IMPORT_TYPES:
            raise ValueError(f"Unsupported data_type '{data_type}'.")
        if not files:
            raise ValueError("No files were uploaded.")

        records: list[dict[str, Any]] = []
        for upload in files:
            filename = Path(upload.filename or "uploaded-file").name
            record = {
                "import_id": uuid4().hex[:JOB_ID_LENGTH],
                "created_at": utc_now(),
                "data_type": normalized_type,
                "source_name": filename,
                "source_path": "browser-upload",
                "time_granularity": time_granularity,
                "station_code": station_code or "2586",
            }
            suffix = Path(filename).suffix.lower()
            if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
                records.append(
                    self.store.append_import(
                        {
                            **record,
                            "status": FAILED_STATUS,
                            "message": "Unsupported file format.",
                        }
                    )
                )
                continue

            target_path = self._import_target_path(normalized_type, record["import_id"], filename)
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with target_path.open("wb") as handle:
                    shutil.copyfileobj(upload.file, handle)
            except OSError as exc:
                records.append(
                    self.store.append_import(
                        {
                            **record,
                            "status": FAILED_STATUS,
                            "message": f"{IMPORT_COPY_FAILURE_PREFIX}{exc}",
                        }
                    )
                )
                continue
            finally:
                upload.file.close()

            finalized_record = {
                **record,
                "status": IMPORTED_STATUS,
                "stored_path": str(target_path),
                "file_size_bytes": target_path.stat().st_size,
            }
            rows_detected = self._detect_rows(target_path)
            if rows_detected is not None:
                finalized_record["rows_detected"] = rows_detected
            records.append(self.store.append_import(finalized_record))

        return {
            "uploaded_count": len([item for item in records if item.get("status") == IMPORTED_STATUS]),
            "records": records,
        }

    def create_prediction_job(
        self, payload: PredictionJobCreateRequest
    ) -> dict[str, Any]:
        config_path = self._resolve_config_path(payload.config_path)
        paths = self._reserve_job_paths()
        job_id = paths.run_root.name
        config_snapshot_path = self._materialize_job_config(
            run_root=paths.run_root,
            output_root=paths.output_root,
            config_path=config_path,
        )
        record = self._build_job_record(
            job_id=job_id,
            payload=payload,
            config_path=config_path,
            config_snapshot_path=config_snapshot_path,
            paths=paths,
        )

        if payload.use_existing_artifacts:
            return self._complete_existing_artifact_job(record, paths, config_snapshot_path)
        return self._launch_prediction_job(record, paths, config_snapshot_path)

    def list_jobs(self) -> list[dict[str, Any]]:
        refreshed: list[dict[str, Any]] = []
        for job in self.store.list_jobs():
            job_id = job.get("job_id")
            if not job_id:
                continue
            try:
                refreshed.append(self.refresh_job(job_id))
            except Exception as exc:
                refreshed.append(self._failed_refresh_view(job, exc))
        return sorted(
            refreshed,
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )

    def refresh_job(self, job_id: str) -> dict[str, Any]:
        record = self.store.get_job(job_id)
        if record is None:
            raise KeyError(job_id)

        process = self._get_process(job_id)
        if process is not None and record.get("status") == RUNNING_STATUS:
            return_code = process.poll()
            if return_code is None:
                return self._attach_log_preview(record)
            self._discard_process(job_id)
            return self._attach_log_preview(
                self._reconcile_job_state(record, observed_return_code=return_code)
            )

        if record.get("status") not in self.TERMINAL_STATUSES:
            record = self._reconcile_job_state(record)
        return self._attach_log_preview(record)

    def get_job_series(self, job_id: str) -> dict[str, Any]:
        record = self.refresh_job(job_id)
        if record.get("status") != COMPLETED_STATUS:
            raise RuntimeError("Job artifacts are not ready yet.")
        return self.get_job_repository(job_id, require_completed=True).predictions(
            model=record.get("model_name"),
            split="test",
        )

    def get_job_repository(
        self, job_id: str, require_completed: bool = False
    ) -> ArtifactRepository:
        record = self.refresh_job(job_id)
        if require_completed and record.get("status") != COMPLETED_STATUS:
            raise RuntimeError("Job artifacts are not ready yet.")
        return self._repository_from_record(record)

    def _build_import_record(
        self,
        payload: DataImportRequest,
        source: Path,
    ) -> dict[str, Any]:
        return {
            "import_id": uuid4().hex[:JOB_ID_LENGTH],
            "created_at": utc_now(),
            "data_type": payload.data_type,
            "source_name": payload.source_name,
            "source_path": str(source),
            "time_granularity": payload.time_granularity,
            "station_code": payload.station_code,
        }

    def _append_import_failure(self, record: dict[str, Any], message: str) -> dict[str, Any]:
        return self.store.append_import({**record, "status": FAILED_STATUS, "message": message})

    def _import_target_path(self, data_type: str, import_id: str, source_name: str) -> Path:
        return self.settings.imports_root / data_type / f"{import_id}-{source_name}"

    def _resolve_config_path(self, config_path: str | None) -> Path:
        resolved = (
            Path(config_path).expanduser().resolve()
            if config_path
            else self.settings.default_config_path
        )
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"Config file not found: {resolved}")
        return resolved

    def _reserve_job_paths(self) -> JobRuntimePaths:
        for _ in range(8):
            candidate = uuid4().hex[:JOB_ID_LENGTH]
            paths = self._job_paths(candidate)
            try:
                paths.run_root.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                continue
            return paths
        raise RuntimeError("Unable to allocate a unique job id.")

    def _job_paths(self, job_id: str) -> JobRuntimePaths:
        paths = JobRuntimePaths.build(self.settings.job_runs_root, job_id)
        self._assert_managed_path(paths.run_root)
        return paths

    def _assert_managed_path(self, path: Path) -> Path:
        resolved = path.resolve()
        managed_root = self.settings.job_runs_root.resolve()
        if resolved == managed_root or managed_root not in resolved.parents:
            raise ValueError(f"Refusing to operate outside job runs root: {resolved}")
        return resolved

    def _build_job_record(
        self,
        *,
        job_id: str,
        payload: PredictionJobCreateRequest,
        config_path: Path,
        config_snapshot_path: Path,
        paths: JobRuntimePaths,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        return {
            "job_id": job_id,
            "created_at": timestamp,
            "updated_at": timestamp,
            "mode": payload.mode,
            "model_name": payload.model_name,
            "station_code": payload.station_code,
            "config_path": str(config_path),
            "config_snapshot_path": str(config_snapshot_path),
            "start_date": payload.start_date,
            "end_date": payload.end_date,
            "use_existing_artifacts": payload.use_existing_artifacts,
            "runtime_root": str(self.settings.runtime_root),
            "run_root": str(paths.run_root),
            "artifact_root": str(paths.output_root),
            "status_file": str(paths.status_file),
            "stdout_log": str(paths.stdout_log),
            "stderr_log": str(paths.stderr_log),
        }

    def _complete_existing_artifact_job(
        self,
        record: dict[str, Any],
        paths: JobRuntimePaths,
        config_snapshot_path: Path,
    ) -> dict[str, Any]:
        self._snapshot_integrated_outputs(paths.output_root)
        scoped_repo = self.repository.scoped(
            outputs_root=paths.output_root,
            config_path=config_snapshot_path,
        )
        finished_at = utc_now()
        completed_record = {
            **record,
            "status": COMPLETED_STATUS,
            "finished_at": finished_at,
            "message": EXISTING_ARTIFACT_MESSAGE,
            "artifacts": scoped_repo.artifact_manifest(),
        }
        self._write_status_file(
            paths.status_file,
            {
                "status": COMPLETED_STATUS,
                "started_at": record["created_at"],
                "finished_at": finished_at,
                "return_code": 0,
                "artifact_root": str(paths.output_root),
                "message": EXISTING_ARTIFACT_MESSAGE,
            },
        )
        return self.store.append_job(completed_record)

    def _snapshot_integrated_outputs(self, output_root: Path) -> None:
        safe_output_root = self._assert_managed_path(output_root)
        source_root = self.settings.outputs_root
        if not source_root.exists() or not source_root.is_dir():
            raise FileNotFoundError(f"Integrated outputs root not found: {source_root}")

        staging_root = safe_output_root.parent / f".{safe_output_root.name}.tmp-{uuid4().hex[:8]}"
        if staging_root.exists():
            shutil.rmtree(staging_root)

        try:
            shutil.copytree(source_root, staging_root)
            if safe_output_root.exists():
                shutil.rmtree(safe_output_root)
            staging_root.replace(safe_output_root)
        except Exception:
            if staging_root.exists():
                shutil.rmtree(staging_root, ignore_errors=True)
            raise

    def _launch_prediction_job(
        self,
        record: dict[str, Any],
        paths: JobRuntimePaths,
        config_snapshot_path: Path,
    ) -> dict[str, Any]:
        command = self._job_runner_command(config_snapshot_path, paths)
        process = self._spawn_process(command, paths.stdout_log, paths.stderr_log)
        job_id = str(record["job_id"])
        started_at = utc_now()
        running_record = {
            **record,
            "status": RUNNING_STATUS,
            "started_at": started_at,
            "pid": process.pid,
            "command": command,
            "message": LAUNCHED_MESSAGE,
        }
        with self._process_lock:
            self._processes[job_id] = process
        try:
            self._write_status_file(
                paths.status_file,
                {
                    "status": RUNNING_STATUS,
                    "started_at": started_at,
                    "artifact_root": str(paths.output_root),
                    "pid": process.pid,
                    "message": LAUNCHED_MESSAGE,
                },
            )
            return self.store.append_job(running_record)
        except Exception:
            self._cleanup_failed_launch(job_id, process, paths.status_file)
            raise

    def _job_runner_command(
        self,
        config_snapshot_path: Path,
        paths: JobRuntimePaths,
    ) -> list[str]:
        return [
            sys.executable,
            "-m",
            JOB_RUNNER_MODULE,
            "--runtime-root",
            str(self.settings.runtime_root),
            "--config",
            str(config_snapshot_path),
            "--status-file",
            str(paths.status_file),
            "--artifact-root",
            str(paths.output_root),
        ]

    def _spawn_process(
        self,
        command: list[str],
        stdout_log: Path,
        stderr_log: Path,
    ) -> subprocess.Popen[Any]:
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stdout_handle = stdout_log.open("w", encoding="utf-8")
        stderr_handle = stderr_log.open("w", encoding="utf-8")
        try:
            return subprocess.Popen(
                command,
                cwd=str(self.settings.project_root),
                stdout=stdout_handle,
                stderr=stderr_handle,
                creationflags=CREATE_NO_WINDOW,
            )
        finally:
            stdout_handle.close()
            stderr_handle.close()

    def _cleanup_failed_launch(
        self,
        job_id: str,
        process: subprocess.Popen[Any],
        status_file: Path,
    ) -> None:
        self._discard_process(job_id)
        self._terminate_process(process)
        try:
            self._write_status_file(
                status_file,
                {
                    "status": FAILED_STATUS,
                    "finished_at": utc_now(),
                    "return_code": -1,
                    "message": "Job launch failed before state persistence completed.",
                },
            )
        except OSError:
            pass

    def _terminate_process(self, process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _materialize_job_config(
        self,
        run_root: Path,
        output_root: Path,
        config_path: Path,
    ) -> Path:
        resolved = copy.deepcopy(self._load_config_mapping(config_path))
        resolved["output_dir"] = str(output_root)
        resolved["hydrodynamics"] = self._resolved_hydrodynamics_config(resolved, output_root)
        resolved["ndti"] = self._resolved_ndti_config(resolved, output_root)

        snapshot_path = run_root / "configs" / f"{config_path.stem}-job.yaml"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            yaml.safe_dump(resolved, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return snapshot_path

    def _load_config_mapping(self, config_path: Path) -> dict[str, Any]:
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"Failed to read config file: {config_path}: {exc}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse config file: {config_path}: {exc}") from exc
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Config file must decode to a mapping: {config_path}")
        return loaded

    def _resolved_hydrodynamics_config(
        self,
        config: dict[str, Any],
        output_root: Path,
    ) -> dict[str, Any]:
        hydrodynamics = dict(config.get("hydrodynamics", {}))
        hydrodynamics_output_dir = output_root / HYDRODYNAMICS_OUTPUT_DIR_NAME
        hydrodynamics["output_dir"] = str(hydrodynamics_output_dir)
        hydrodynamics["wide_path"] = str(
            hydrodynamics_output_dir / HYDRODYNAMICS_WIDE_FILENAME
        )
        return hydrodynamics

    def _resolved_ndti_config(
        self,
        config: dict[str, Any],
        output_root: Path,
    ) -> dict[str, Any]:
        ndti = dict(config.get("ndti", {}))
        ndti["output_dir"] = str(output_root / NDTI_OUTPUT_DIR_NAME)
        return ndti

    def _write_status_file(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def _read_status_file(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, JSONDecodeError):
            return None

    def _reconcile_job_state(
        self,
        record: dict[str, Any],
        observed_return_code: int | None = None,
    ) -> dict[str, Any]:
        status_payload = self._status_payload(record)
        if status_payload and status_payload.get("status") in self.TERMINAL_STATUSES:
            return self.store.update_job(
                str(record["job_id"]),
                self._terminal_status_updates(record, status_payload),
            )

        if observed_return_code is not None:
            return self.store.update_job(
                str(record["job_id"]),
                self._process_exit_updates(record, observed_return_code),
            )

        if self._is_detached_running(record):
            return self._detached_running_record(record)

        if record.get("status") == RUNNING_STATUS:
            return self.store.update_job(
                str(record["job_id"]),
                {
                    "status": ORPHANED_STATUS,
                    "finished_at": utc_now(),
                    "updated_at": utc_now(),
                    "return_code": -1,
                    "message": ORPHANED_MESSAGE,
                },
            )
        return record

    def _status_payload(self, record: dict[str, Any]) -> dict[str, Any] | None:
        status_file = record.get("status_file")
        if not status_file:
            return None
        return self._read_status_file(Path(str(status_file)))

    def _terminal_status_updates(
        self,
        record: dict[str, Any],
        status_payload: dict[str, Any],
    ) -> dict[str, Any]:
        final_status = str(status_payload.get("status"))
        finished_at = status_payload.get("finished_at") or utc_now()
        updates = {
            "status": final_status,
            "finished_at": finished_at,
            "updated_at": finished_at,
            "return_code": self._coerce_return_code(status_payload.get("return_code"), default=0),
            "message": status_payload.get("message")
            or status_payload.get("error")
            or record.get("message")
            or f"Job {final_status}.",
        }
        return self._validated_completion_updates(record, updates)

    def _process_exit_updates(
        self,
        record: dict[str, Any],
        return_code: int,
    ) -> dict[str, Any]:
        final_status = COMPLETED_STATUS if return_code == 0 else FAILED_STATUS
        updates = {
            "status": final_status,
            "finished_at": utc_now(),
            "updated_at": utc_now(),
            "return_code": return_code,
            "message": COMPLETED_MESSAGE if final_status == COMPLETED_STATUS else f"Job {final_status}.",
        }
        return self._validated_completion_updates(record, updates)

    def _validated_completion_updates(
        self,
        record: dict[str, Any],
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        if updates.get("status") != COMPLETED_STATUS:
            return updates
        manifest = self._verified_artifact_manifest(record)
        if manifest is None:
            return {
                **updates,
                "status": FAILED_STATUS,
                "return_code": updates.get("return_code", -1) if updates.get("return_code", -1) != 0 else -1,
                "message": ARTIFACT_VALIDATION_FAILURE_MESSAGE,
            }
        return {**updates, "artifacts": manifest}

    def _verified_artifact_manifest(self, record: dict[str, Any]) -> dict[str, str] | None:
        artifact_root = record.get("artifact_root")
        if not artifact_root:
            return None
        artifact_path = Path(str(artifact_root))
        if not artifact_path.exists():
            return None
        try:
            repository = self._repository_from_record(record)
            repository.assert_source_ready()
            return repository.artifact_manifest()
        except Exception:
            return None

    def _is_detached_running(self, record: dict[str, Any]) -> bool:
        pid = record.get("pid")
        return isinstance(pid, int) and self._pid_exists(pid)

    def _detached_running_record(self, record: dict[str, Any]) -> dict[str, Any]:
        current_message = record.get("message") or "Job is running."
        if "detached" in current_message.lower() or self._get_process(str(record["job_id"])) is not None:
            return record
        return self.store.update_job(
            str(record["job_id"]),
            {
                "updated_at": utc_now(),
                "message": DETACHED_WAIT_MESSAGE,
            },
        )

    def _failed_refresh_view(self, record: dict[str, Any], exc: Exception) -> dict[str, Any]:
        return {
            **record,
            "status": FAILED_STATUS,
            "updated_at": utc_now(),
            "message": f"Refresh failed: {type(exc).__name__}: {exc}",
        }

    def _get_process(self, job_id: str) -> subprocess.Popen[Any] | None:
        with self._process_lock:
            return self._processes.get(job_id)

    def _discard_process(self, job_id: str) -> None:
        with self._process_lock:
            self._processes.pop(job_id, None)

    def _attach_log_preview(self, record: dict[str, Any]) -> dict[str, Any]:
        previews = {
            key.replace("_log", "_preview"): self._tail(Path(str(path_value)))
            for key in ("stdout_log", "stderr_log")
            if (path_value := record.get(key))
        }
        return {**record, **previews} if previews else record

    def _tail(self, path: Path, line_count: int = LOG_PREVIEW_LINE_COUNT) -> list[str]:
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError as exc:
            return [f"Log preview unavailable: {exc}"]
        return lines[-line_count:]

    def _detect_rows(self, path: Path) -> int | None:
        suffix = path.suffix.lower()
        try:
            if suffix == ".csv":
                return int(len(pd.read_csv(path)))
            if suffix in {".xls", ".xlsx"}:
                return int(len(pd.read_excel(path)))
            if suffix == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                return len(payload) if isinstance(payload, list) else 1
        except Exception:
            return None
        return None

    def _pid_exists(self, pid: int) -> bool:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            synchronize = 0x00100000
            query_limited_information = 0x1000
            process = ctypes.windll.kernel32.OpenProcess(
                synchronize | query_limited_information,
                0,
                pid,
            )
            if process == 0:
                return False
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(process)
            return int(exit_code.value) == ACTIVE_PROCESS_EXIT_CODE
        try:
            import os

            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _repository_from_record(self, record: dict[str, Any]) -> ArtifactRepository:
        artifact_root = record.get("artifact_root")
        if not artifact_root:
            raise RuntimeError("Job has no artifact root.")
        config_snapshot_path = record.get("config_snapshot_path")
        return self.repository.scoped(
            outputs_root=Path(str(artifact_root)),
            config_path=(
                Path(str(config_snapshot_path))
                if config_snapshot_path
                else self.settings.default_config_path
            ),
        )

    def _coerce_return_code(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
