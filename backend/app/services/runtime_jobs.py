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

from backend.app.config import Settings
from backend.app.domain.codes import ErrorCode, JobStatus, TERMINAL_JOB_STATUSES
from backend.app.domain.models import MODEL_KEYS, is_known_model, models_for_request
from backend.app.schemas import PredictionJobCreateRequest
from backend.app.services.artifact_repository import ArtifactRepository
from backend.app.services.state_store import JOBS_TABLE, SqliteStateStore
from backend.app.services.task_progress import task_view

JOB_ID_LENGTH = 12
LOG_PREVIEW_LINE_COUNT = 20
QUEUED_STATUS = str(JobStatus.QUEUED)
RUNNING_STATUS = str(JobStatus.RUNNING)
CANCELLING_STATUS = str(JobStatus.CANCELLING)
CANCELLED_STATUS = str(JobStatus.CANCELLED)
COMPLETED_STATUS = str(JobStatus.COMPLETED)
FAILED_STATUS = str(JobStatus.FAILED)
TIMEOUT_STATUS = str(JobStatus.TIMEOUT)
ORPHANED_STATUS = str(JobStatus.ORPHANED)
TERMINAL_STATUSES = {str(status) for status in TERMINAL_JOB_STATUSES}
#: Statuses that occupy a concurrency slot.
OCCUPYING_STATUSES = {RUNNING_STATUS, CANCELLING_STATUS}
QUEUED_MESSAGE = "Waiting for a free execution slot."
CANCEL_REQUESTED_MESSAGE = "Cancellation requested; stopping the run."
CANCELLED_MESSAGE = "Job cancelled."
TIMEOUT_MESSAGE_TEMPLATE = "Job exceeded the {seconds}s time limit and was stopped."
DEFAULT_JOB_PRIORITY = 5
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
#: Written by run_full_pipeline.py with the scope it actually applied.
RUN_SCOPE_FILENAME = "run_scope.json"
ACTIVE_PROCESS_EXIT_CODE = 259


class JobParameterError(ValueError):
    """A job was submitted with parameters that cannot be honoured."""

    def __init__(self, code: ErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


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
        # Serializes queue draining: two concurrent requests must not both
        # decide there is one free slot and start a job into it.
        self._dispatch_lock = threading.RLock()
        self.settings.imports_root.mkdir(parents=True, exist_ok=True)
        self.settings.job_logs_root.mkdir(parents=True, exist_ok=True)
        self.settings.job_runs_root.mkdir(parents=True, exist_ok=True)

    def create_prediction_job(
        self,
        payload: PredictionJobCreateRequest,
        *,
        coverage: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        """Start a job, or refuse it before anything expensive happens.

        ``coverage`` is the ``(start, end)`` window the selected datasets
        actually cover; the API layer reads it from :class:`DatasetService`. When
        supplied, a requested range outside it is rejected here rather than
        discovered hours into a run.
        """
        self.validate_job_parameters(payload, coverage=coverage)
        config_path = self._resolve_config_path(payload.config_path)
        paths = self._reserve_job_paths()
        job_id = paths.run_root.name
        config_snapshot_path = self._materialize_job_config(
            run_root=paths.run_root,
            output_root=paths.output_root,
            config_path=config_path,
            payload=payload,
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
        if self._free_slots() <= 0:
            # Review item 10: the old service spawned a pipeline per request with
            # no ceiling, so two impatient clicks could put two trainings on one
            # machine. Over quota, the job waits in the queue instead.
            return self._enqueue_prediction_job(record, paths)
        return self._launch_prediction_job(record, paths, config_snapshot_path)

    # -- queue -------------------------------------------------------------

    def _active_jobs(self) -> list[dict[str, Any]]:
        return [
            job
            for job in self.store.list_jobs()
            if str(job.get("status", "")) in OCCUPYING_STATUSES
        ]

    def _free_slots(self) -> int:
        return max(0, int(self.settings.max_concurrent_jobs) - len(self._active_jobs()))

    def _enqueue_prediction_job(
        self,
        record: dict[str, Any],
        paths: JobRuntimePaths,
    ) -> dict[str, Any]:
        queued_at = utc_now()
        queued_record = {
            **record,
            "status": QUEUED_STATUS,
            "queued_at": queued_at,
            "updated_at": queued_at,
            "stage": QUEUED_STATUS,
            "message": QUEUED_MESSAGE,
        }
        self._write_status_file(
            paths.status_file,
            {
                "status": QUEUED_STATUS,
                "queued_at": queued_at,
                "artifact_root": str(paths.output_root),
                "message": QUEUED_MESSAGE,
            },
        )
        return self.store.append_job(queued_record)

    def queued_jobs(self) -> list[dict[str, Any]]:
        """Waiting jobs, in the order they will run.

        Higher priority first, then oldest first — so a routine batch cannot
        starve an urgent re-run, and equal-priority work stays fair.
        """
        queued = [
            job for job in self.store.list_jobs() if str(job.get("status", "")) == QUEUED_STATUS
        ]
        return sorted(
            queued,
            key=lambda job: (
                -int(job.get("priority") or DEFAULT_JOB_PRIORITY),
                str(job.get("queued_at") or job.get("created_at") or ""),
            ),
        )

    def dispatch_queue(self) -> list[dict[str, Any]]:
        """Start as many waiting jobs as there is capacity for.

        Called whenever job state is read or written, so the queue drains
        without a background thread — one process, one scheduler, no risk of two
        workers claiming the same job.
        """
        started: list[dict[str, Any]] = []
        with self._dispatch_lock:
            for job in self.queued_jobs():
                if self._free_slots() <= 0:
                    break
                job_id = str(job["job_id"])
                snapshot = job.get("config_snapshot_path")
                if not snapshot:
                    started.append(self._fail_job(job_id, "Queued job lost its config snapshot."))
                    continue
                try:
                    started.append(
                        self._launch_prediction_job(job, self._job_paths(job_id), Path(str(snapshot)))
                    )
                except Exception as exc:  # noqa: BLE001 - the queue must survive one bad job
                    started.append(self._fail_job(job_id, f"Failed to start queued job: {exc}"))
        return started

    def _fail_job(self, job_id: str, message: str) -> dict[str, Any]:
        return self.store.update_job(
            job_id,
            {
                "status": FAILED_STATUS,
                "finished_at": utc_now(),
                "updated_at": utc_now(),
                "return_code": -1,
                "message": message,
            },
        )

    def queue_snapshot(self) -> dict[str, Any]:
        """What the task centre shows above the job list."""
        jobs = self.store.list_jobs()
        by_status: dict[str, int] = {}
        for job in jobs:
            status = str(job.get("status", ""))
            by_status[status] = by_status.get(status, 0) + 1
        return {
            "max_concurrent_jobs": int(self.settings.max_concurrent_jobs),
            "running": by_status.get(RUNNING_STATUS, 0),
            "queued": by_status.get(QUEUED_STATUS, 0),
            "free_slots": self._free_slots(),
            "by_status": by_status,
            "job_timeout_seconds": int(self.settings.job_timeout_seconds),
        }

    # -- cancel / retry ----------------------------------------------------

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        """Stop a job. Queued work stops immediately; a running process is killed."""
        record = self.store.get_job(job_id)
        if record is None:
            raise KeyError(job_id)
        status = str(record.get("status", ""))

        if status in TERMINAL_STATUSES:
            raise JobParameterError(
                ErrorCode.JOB_NOT_CANCELLABLE,
                f"Job {job_id} already finished with status '{status}'.",
            )

        if status == QUEUED_STATUS:
            cancelled = self.store.update_job(
                job_id,
                {
                    "status": CANCELLED_STATUS,
                    "finished_at": utc_now(),
                    "updated_at": utc_now(),
                    "message": CANCELLED_MESSAGE,
                },
            )
            self.dispatch_queue()
            return cancelled

        self.store.update_job(
            job_id,
            {
                "status": CANCELLING_STATUS,
                "updated_at": utc_now(),
                "message": CANCEL_REQUESTED_MESSAGE,
            },
        )
        self._stop_running_job(job_id, record)
        cancelled = self.store.update_job(
            job_id,
            {
                "status": CANCELLED_STATUS,
                "finished_at": utc_now(),
                "updated_at": utc_now(),
                "return_code": -1,
                "message": CANCELLED_MESSAGE,
            },
        )
        self.dispatch_queue()
        return cancelled

    def _stop_running_job(self, job_id: str, record: dict[str, Any]) -> None:
        """Kill the job's process, whether we own its handle or only its pid."""
        process = self._get_process(job_id)
        if process is not None:
            self._terminate_process(process)
            self._discard_process(job_id)
            return
        pid = record.get("pid")
        if isinstance(pid, int) and self._pid_exists(pid):
            import os
            import signal

            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

    def retry_job(self, job_id: str) -> dict[str, Any]:
        """Resubmit a finished job with the parameters it was originally given.

        A retry is a new job, not a mutation of the old one: the failed run stays
        readable so the failure can still be diagnosed after the retry succeeds.
        """
        record = self.store.get_job(job_id)
        if record is None:
            raise KeyError(job_id)
        status = str(record.get("status", ""))
        if status not in TERMINAL_STATUSES:
            raise JobParameterError(
                ErrorCode.INVALID_STATE_TRANSITION,
                f"Job {job_id} is '{status}'; cancel it before retrying.",
            )

        requested = record.get("requested_parameters") or {}
        payload = PredictionJobCreateRequest(
            model_name=str(requested.get("model_name") or record.get("model_name") or "cmfbe_stgcn"),
            station_code=str(requested.get("station_code") or record.get("station_code") or "2586"),
            config_path=record.get("config_path"),
            start_date=requested.get("start_date") or record.get("start_date"),
            end_date=requested.get("end_date") or record.get("end_date"),
            use_existing_artifacts=bool(record.get("use_existing_artifacts", False)),
            case_id=record.get("case_id"),
            priority=int(record.get("priority") or DEFAULT_JOB_PRIORITY),
        )
        retried = self.create_prediction_job(payload)
        return self.store.update_job(
            str(retried["job_id"]),
            {"retry_of": job_id, "retry_count": int(record.get("retry_count") or 0) + 1},
        )

    # -- timeout -----------------------------------------------------------

    def _timed_out(self, record: dict[str, Any]) -> bool:
        limit = int(self.settings.job_timeout_seconds)
        if limit <= 0 or str(record.get("status", "")) != RUNNING_STATUS:
            return False
        started = record.get("started_at") or record.get("created_at")
        if not started:
            return False
        try:
            begin = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        except ValueError:
            return False
        if begin.tzinfo is None:
            begin = begin.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - begin).total_seconds() > limit

    def _time_out_job(self, record: dict[str, Any]) -> dict[str, Any]:
        job_id = str(record["job_id"])
        self._stop_running_job(job_id, record)
        timed_out = self.store.update_job(
            job_id,
            {
                "status": TIMEOUT_STATUS,
                "finished_at": utc_now(),
                "updated_at": utc_now(),
                "return_code": -1,
                "message": TIMEOUT_MESSAGE_TEMPLATE.format(
                    seconds=int(self.settings.job_timeout_seconds)
                ),
            },
        )
        self.dispatch_queue()
        return timed_out

    # -- logs and retention ------------------------------------------------

    def log_path(self, job_id: str, stream: str) -> Path:
        """The on-disk log for a job, for download.

        ``stream`` is validated against a fixed pair rather than interpolated,
        so this cannot be turned into a read of an arbitrary file.
        """
        record = self.store.get_job(job_id)
        if record is None:
            raise KeyError(job_id)
        key = {"stdout": "stdout_log", "stderr": "stderr_log"}.get(stream)
        if key is None:
            raise JobParameterError(
                ErrorCode.VALIDATION_FAILED,
                f"Unknown log stream '{stream}'. Use 'stdout' or 'stderr'.",
            )
        raw = record.get(key)
        if not raw:
            raise FileNotFoundError(f"Job {job_id} has no {stream} log.")
        path = Path(str(raw))
        if not path.exists():
            raise FileNotFoundError(f"Job {job_id} {stream} log is no longer on disk.")
        return path

    def job_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        """Every file the run produced, with size — the task centre's output list."""
        record = self.refresh_job(job_id)
        artifact_root = record.get("artifact_root")
        if not artifact_root:
            return []
        root = Path(str(artifact_root))
        if not root.exists():
            return []
        entries: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            entries.append(
                {
                    "relative_path": str(path.relative_to(root)),
                    "size_bytes": size,
                    "category": path.relative_to(root).parts[0] if path.parent != root else "root",
                }
            )
        return entries

    def purge_expired_jobs(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Delete run directories past the retention window (review item 26).

        Only terminal jobs are eligible, and the state record is removed with the
        directory so the task centre never lists a run whose artifacts are gone.
        """
        days = int(self.settings.job_run_retention_days)
        if days <= 0:
            return {"removed": [], "retention_days": days, "skipped": "retention_disabled"}
        cutoff = (now or datetime.now(timezone.utc)).timestamp() - days * 86400
        removed: list[str] = []
        for job in self.store.list_jobs():
            if str(job.get("status", "")) not in TERMINAL_STATUSES:
                continue
            finished = job.get("finished_at") or job.get("updated_at") or job.get("created_at")
            try:
                stamp = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            if stamp.timestamp() > cutoff:
                continue
            job_id = str(job["job_id"])
            run_root = job.get("run_root")
            if run_root:
                try:
                    shutil.rmtree(self._assert_managed_path(Path(str(run_root))), ignore_errors=True)
                except ValueError:
                    pass
            self.store.delete(JOBS_TABLE, job_id)
            removed.append(job_id)
        return {"removed": removed, "retention_days": days}

    def validate_job_parameters(
        self,
        payload: PredictionJobCreateRequest,
        *,
        coverage: tuple[str, str] | None = None,
    ) -> None:
        """Reject a job whose parameters cannot be satisfied.

        Review item 1: the old submit path accepted anything and let the run
        fail — or worse, quietly ignore the parameter and return results for a
        different scope. Everything checkable is checked here instead.
        """
        if not is_known_model(payload.model_name):
            raise JobParameterError(
                ErrorCode.VALIDATION_FAILED,
                f"Unknown model '{payload.model_name}'. Available: {list(MODEL_KEYS)}.",
            )

        start = self._parse_job_date(payload.start_date, field="start_date")
        end = self._parse_job_date(payload.end_date, field="end_date")
        if start and end and start > end:
            raise JobParameterError(
                ErrorCode.VALIDATION_FAILED,
                f"start_date {payload.start_date} is after end_date {payload.end_date}.",
            )

        if coverage is None:
            return
        coverage_start, coverage_end = coverage
        if start and str(start.date()) < coverage_start:
            raise JobParameterError(
                ErrorCode.DATE_RANGE_OUT_OF_COVERAGE,
                f"start_date {payload.start_date} precedes the available data, "
                f"which starts {coverage_start}.",
            )
        if end and str(end.date()) > coverage_end:
            raise JobParameterError(
                ErrorCode.DATE_RANGE_OUT_OF_COVERAGE,
                f"end_date {payload.end_date} exceeds the available data, "
                f"which ends {coverage_end}.",
            )

    @staticmethod
    def _parse_job_date(value: str | None, *, field: str) -> pd.Timestamp | None:
        if value in (None, ""):
            return None
        try:
            return pd.Timestamp(str(value))
        except (ValueError, TypeError) as exc:
            raise JobParameterError(
                ErrorCode.VALIDATION_FAILED,
                f"{field} '{value}' is not a valid date.",
            ) from exc

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
            [task_view(job) for job in refreshed],
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )

    def refresh_job(self, job_id: str) -> dict[str, Any]:
        record = self.store.get_job(job_id)
        if record is None:
            raise KeyError(job_id)

        if record.get("status") == QUEUED_STATUS:
            # Reading a queued job is a chance to see whether it can start now.
            self.dispatch_queue()
            record = self.store.get_job(job_id) or record

        process = self._get_process(job_id)
        if process is not None and record.get("status") == RUNNING_STATUS:
            return_code = process.poll()
            if return_code is None:
                if self._timed_out(record):
                    return self._time_out_job(record)
                return self._attach_log_preview(record)
            self._discard_process(job_id)
            return self._attach_log_preview(
                self._reconcile_job_state(record, observed_return_code=return_code)
            )

        if record.get("status") not in self.TERMINAL_STATUSES:
            # Reconcile against the on-disk status file first: a job that finished
            # is reported as finished before its age is judged.
            record = self._reconcile_job_state(record)
        if record.get("status") == RUNNING_STATUS and self._timed_out(record):
            return self._time_out_job(record)
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
            "model_name": payload.model_name,
            "station_code": payload.station_code,
            # The case this run answers for. Projected as a column so the task
            # centre and the case view can find each other's records.
            "case_id": payload.case_id,
            "priority": payload.priority,
            "config_path": str(config_path),
            "config_snapshot_path": str(config_snapshot_path),
            "start_date": payload.start_date,
            "end_date": payload.end_date,
            "use_existing_artifacts": payload.use_existing_artifacts,
            # What the caller asked for. The pipeline writes what it actually
            # applied to metrics/run_scope.json, which `refresh_job` reads back
            # as `effective_parameters` — the two are reported separately so a
            # silently-clipped date range is visible rather than assumed.
            "requested_parameters": {
                "model_name": payload.model_name,
                "models": models_for_request(payload.model_name),
                "station_code": payload.station_code,
                "start_date": payload.start_date,
                "end_date": payload.end_date,
            },
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
        payload: PredictionJobCreateRequest | None = None,
    ) -> Path:
        resolved = copy.deepcopy(self._load_config_mapping(config_path))
        resolved["output_dir"] = str(output_root)
        resolved["hydrodynamics"] = self._resolved_hydrodynamics_config(resolved, output_root)
        resolved["ndti"] = self._resolved_ndti_config(resolved, output_root)
        if payload is not None:
            resolved["run_scope"] = self._resolved_run_scope(resolved, payload)
            resolved["models"] = self._resolved_model_selection(resolved, payload)

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

    def _resolved_run_scope(
        self,
        config: dict[str, Any],
        payload: PredictionJobCreateRequest,
    ) -> dict[str, Any]:
        """Write the requested station and date range into the config snapshot.

        Review item 1: these were collected by the UI, stored on the job record
        and then never reached the pipeline. The snapshot is the only thing the
        runner hands to ``run_full_pipeline.py``, so the parameters have to live
        here to take effect.
        """
        run_scope = dict(config.get("run_scope") or {})
        run_scope["station_code"] = payload.station_code or run_scope.get("station_code")
        run_scope["start_date"] = payload.start_date or None
        run_scope["end_date"] = payload.end_date or None
        return run_scope

    def _resolved_model_selection(
        self,
        config: dict[str, Any],
        payload: PredictionJobCreateRequest,
    ) -> dict[str, Any]:
        """Narrow ``models.enabled`` to the requested model plus its dependencies.

        The requested model is kept first so it is the one the job reports on;
        :data:`REQUIRED_MODEL_KEYS` models are appended because the threshold,
        sensitivity and agent-context artifacts are derived from them.
        """
        models = dict(config.get("models") or {})
        requested = str(payload.model_name or "").strip()
        if not requested:
            return models
        models["enabled"] = models_for_request(requested)
        return models

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
        completed = {**updates, "artifacts": manifest}
        effective = self._effective_parameters(record)
        if effective is not None:
            completed["effective_parameters"] = effective
        return completed

    def _effective_parameters(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """What the pipeline actually ran, as it reported it.

        ``run_scope.json`` is written by the pipeline after clipping the dataset,
        so its dates are the real ones — a request for 2020-01-01 against data
        starting 2020-11-02 shows up here as the later date instead of being
        silently assumed to have been honoured.
        """
        artifact_root = record.get("artifact_root")
        if not artifact_root:
            return None
        scope_path = Path(str(artifact_root)) / "metrics" / RUN_SCOPE_FILENAME
        if not scope_path.exists():
            return None
        try:
            payload = json.loads(scope_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

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
