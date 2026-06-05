from __future__ import annotations

import copy
import ctypes
import json
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import yaml

from backend.app.config import Settings
from backend.app.schemas import DataImportRequest, PredictionJobCreateRequest
from backend.app.services.artifact_repository import ArtifactRepository
from backend.app.services.state_store import SqliteStateStore


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RuntimeJobService:
    TERMINAL_STATUSES = {"completed", "failed", "orphaned"}

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
        record = {
            "import_id": uuid4().hex[:12],
            "created_at": utc_now(),
            "data_type": payload.data_type,
            "source_name": payload.source_name,
            "source_path": str(source),
            "time_granularity": payload.time_granularity,
            "station_code": payload.station_code,
        }
        if not source.exists() or not source.is_file():
            record.update(
                {
                    "status": "failed",
                    "message": "Source file does not exist.",
                }
            )
            return self.store.append_import(record)

        target_dir = self.settings.imports_root / payload.data_type
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{record['import_id']}-{source.name}"
        try:
            shutil.copy2(source, target_path)
        except OSError as exc:
            record.update(
                {
                    "status": "failed",
                    "message": f"Copy failed: {exc}",
                }
            )
            return self.store.append_import(record)

        record.update(
            {
                "status": "imported",
                "stored_path": str(target_path),
                "file_size_bytes": target_path.stat().st_size,
            }
        )
        rows_detected = self._detect_rows(target_path)
        if rows_detected is not None:
            record["rows_detected"] = rows_detected
        return self.store.append_import(record)

    def list_imports(self) -> list[dict[str, Any]]:
        return sorted(
            self.store.list_imports(),
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )

    def create_prediction_job(
        self, payload: PredictionJobCreateRequest
    ) -> dict[str, Any]:
        job_id = uuid4().hex[:12]
        config_path = (
            Path(payload.config_path).expanduser().resolve()
            if payload.config_path
            else self.settings.default_config_path
        )
        if not config_path.exists() or not config_path.is_file():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        run_root = self.settings.job_runs_root / job_id
        output_root = run_root / "outputs"
        status_file = run_root / "run_status.json"
        stdout_path = run_root / "logs" / "stdout.log"
        stderr_path = run_root / "logs" / "stderr.log"
        config_snapshot_path = self._materialize_job_config(
            run_root=run_root,
            output_root=output_root,
            config_path=config_path,
        )

        record = {
            "job_id": job_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "mode": payload.mode,
            "model_name": payload.model_name,
            "station_code": payload.station_code,
            "config_path": str(config_path),
            "config_snapshot_path": str(config_snapshot_path),
            "start_date": payload.start_date,
            "end_date": payload.end_date,
            "use_existing_artifacts": payload.use_existing_artifacts,
            "runtime_root": str(self.settings.runtime_root),
            "run_root": str(run_root),
            "artifact_root": str(output_root),
            "status_file": str(status_file),
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }

        if payload.use_existing_artifacts:
            self._snapshot_integrated_outputs(output_root)
            scoped_repo = self.repository.scoped(
                outputs_root=output_root,
                config_path=config_snapshot_path,
            )
            record.update(
                {
                    "status": "completed",
                    "finished_at": utc_now(),
                    "message": "Snapshot created from currently integrated runtime artifacts.",
                    "artifacts": scoped_repo.artifact_manifest(),
                }
            )
            self._write_status_file(
                status_file,
                {
                    "status": "completed",
                    "started_at": record["created_at"],
                    "finished_at": record["finished_at"],
                    "return_code": 0,
                    "artifact_root": str(output_root),
                },
            )
            return self.store.append_job(record)

        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "backend.app.tasks.job_runner",
            "--runtime-root",
            str(self.settings.runtime_root),
            "--config",
            str(config_snapshot_path),
            "--status-file",
            str(status_file),
        ]
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=str(self.settings.project_root),
                stdout=stdout_handle,
                stderr=stderr_handle,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        finally:
            stdout_handle.close()
            stderr_handle.close()

        with self._process_lock:
            self._processes[job_id] = process
        record.update(
            {
                "status": "running",
                "started_at": utc_now(),
                "pid": process.pid,
                "command": command,
                "message": "Pipeline launched in job-scoped runtime directory.",
            }
        )
        self._write_status_file(
            status_file,
            {
                "status": "running",
                "started_at": record["started_at"],
                "artifact_root": str(output_root),
                "pid": process.pid,
            },
        )
        return self.store.append_job(record)

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs = self.store.list_jobs()
        refreshed: list[dict[str, Any]] = []
        for job in jobs:
            job_id = job.get("job_id")
            if not job_id:
                continue
            try:
                refreshed.append(self.refresh_job(job_id))
            except Exception as exc:
                refreshed.append(
                    {
                        **job,
                        "status": "failed",
                        "updated_at": utc_now(),
                        "message": f"Refresh failed: {type(exc).__name__}: {exc}",
                    }
                )
        return sorted(
            refreshed, key=lambda item: item.get("created_at", ""), reverse=True
        )

    def refresh_job(self, job_id: str) -> dict[str, Any]:
        record = self.store.get_job(job_id)
        if record is None:
            raise KeyError(job_id)

        process = self._get_process(job_id)
        if process is not None and record.get("status") == "running":
            return_code = process.poll()
            if return_code is None:
                return self._attach_log_preview(record)
            self._discard_process(job_id)
            record = self._reconcile_job_state(record, observed_return_code=return_code)
            return self._attach_log_preview(record)

        if record.get("status") not in self.TERMINAL_STATUSES:
            record = self._reconcile_job_state(record)

        return self._attach_log_preview(record)

    def get_job_series(self, job_id: str) -> dict[str, Any]:
        record = self.refresh_job(job_id)
        if record.get("status") != "completed":
            raise RuntimeError("Job artifacts are not ready yet.")
        return self.get_job_repository(job_id, require_completed=True).predictions(
            model=record.get("model_name"),
            split="test",
        )

    def get_job_repository(
        self, job_id: str, require_completed: bool = False
    ) -> ArtifactRepository:
        record = self.refresh_job(job_id)
        if require_completed and record.get("status") != "completed":
            raise RuntimeError("Job artifacts are not ready yet.")
        return self._repository_from_record(record)

    def _materialize_job_config(
        self,
        run_root: Path,
        output_root: Path,
        config_path: Path,
    ) -> Path:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        resolved = copy.deepcopy(config)
        resolved["output_dir"] = str(output_root)

        hydrodynamics = dict(resolved.get("hydrodynamics", {}))
        hydrodynamics_output_dir = output_root / "hydrodynamics_preprocessed"
        hydrodynamics["output_dir"] = str(hydrodynamics_output_dir)
        hydrodynamics["wide_path"] = str(
            hydrodynamics_output_dir / "shanghai_hydrodynamics_daily_wide.csv"
        )
        resolved["hydrodynamics"] = hydrodynamics

        ndti = dict(resolved.get("ndti", {}))
        ndti["output_dir"] = str(output_root / "ndti_preprocessed")
        resolved["ndti"] = ndti

        snapshot_path = run_root / "configs" / f"{config_path.stem}-job.yaml"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            yaml.safe_dump(resolved, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return snapshot_path

    def _snapshot_integrated_outputs(self, output_root: Path) -> None:
        if output_root.exists():
            shutil.rmtree(output_root)
        shutil.copytree(self.settings.outputs_root, output_root)

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
        except Exception:
            return None

    def _reconcile_job_state(
        self,
        record: dict[str, Any],
        observed_return_code: int | None = None,
    ) -> dict[str, Any]:
        status_file = Path(record.get("status_file", "")) if record.get("status_file") else None
        status_payload = self._read_status_file(status_file) if status_file else None
        if status_payload and status_payload.get("status") in self.TERMINAL_STATUSES:
            final_status = str(status_payload.get("status"))
            updates = {
                "status": final_status,
                "finished_at": status_payload.get("finished_at") or utc_now(),
                "updated_at": status_payload.get("finished_at") or utc_now(),
                "return_code": int(status_payload.get("return_code", 0)),
                "message": status_payload.get("error")
                or record.get("message")
                or f"Job {final_status}.",
            }
            if record.get("artifact_root") and Path(str(record["artifact_root"])).exists():
                try:
                    updates["artifacts"] = self._repository_from_record(
                        record
                    ).artifact_manifest()
                except Exception:
                    pass
            return self.store.update_job(str(record["job_id"]), updates)

        if observed_return_code is not None:
            final_status = "completed" if observed_return_code == 0 else "failed"
            updates = {
                "status": final_status,
                "finished_at": utc_now(),
                "updated_at": utc_now(),
                "return_code": observed_return_code,
                "message": record.get("message") or f"Job {final_status}.",
            }
            if final_status == "completed":
                try:
                    updates["artifacts"] = self._repository_from_record(
                        record
                    ).artifact_manifest()
                except Exception:
                    pass
            return self.store.update_job(str(record["job_id"]), updates)

        pid = record.get("pid")
        if isinstance(pid, int) and self._pid_exists(pid):
            detached_message = record.get("message") or "Job is running."
            if "detached" not in detached_message.lower() and self._get_process(str(record["job_id"])) is None:
                return self.store.update_job(
                    str(record["job_id"]),
                    {
                        "updated_at": utc_now(),
                        "message": "Job is still running in detached mode; waiting for status file completion.",
                    },
                )
            return record

        if record.get("status") == "running":
            return self.store.update_job(
                str(record["job_id"]),
                {
                    "status": "orphaned",
                    "finished_at": utc_now(),
                    "updated_at": utc_now(),
                    "return_code": -1,
                    "message": "Job process is no longer alive and no completion marker was found.",
                },
            )
        return record

    def _get_process(self, job_id: str) -> subprocess.Popen[Any] | None:
        with self._process_lock:
            return self._processes.get(job_id)

    def _discard_process(self, job_id: str) -> None:
        with self._process_lock:
            self._processes.pop(job_id, None)

    def _attach_log_preview(self, record: dict[str, Any]) -> dict[str, Any]:
        preview = {}
        for key in ("stdout_log", "stderr_log"):
            path_value = record.get(key)
            if path_value:
                preview[key.replace("_log", "_preview")] = self._tail(Path(path_value))
        if preview:
            return {**record, **preview}
        return record

    def _tail(self, path: Path, line_count: int = 20) -> list[str]:
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
                if isinstance(payload, list):
                    return len(payload)
                return 1
        except Exception:
            return None
        return None

    def _pid_exists(self, pid: int) -> bool:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            synchronize = 0x00100000
            process = ctypes.windll.kernel32.OpenProcess(synchronize, 0, pid)
            if process == 0:
                return False
            ctypes.windll.kernel32.CloseHandle(process)
            return True
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
