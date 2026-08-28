"""Tiered health checks (review item 24).

The old ``/healthz`` only answered "are the integrated research artifacts
present?", which told an operator nothing about whether the *service* could keep
serving. The split is now:

* ``/healthz``  — liveness: is the process alive? (load balancer)
* ``/readyz``   — readiness: can we serve traffic? (state DB + disk floor)
* ``/api/v1/health/dependencies`` — DB, executor, disk, state directories
* ``/api/v1/health/model`` — is a published model serving predictions?
* ``/api/v1/health/data`` — how fresh is the latest accepted data?

Each check returns a ``{"status": ..., "checks": {...}}`` shape the route maps to
200/503. Nothing here raises — a failed dependency is reported, not thrown.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.config import Settings
from backend.app.services.state_store import JOBS_TABLE, SqliteStateStore


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _free_disk_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return -1


def _dir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return os.access(path, os.W_OK)
    except OSError:
        return False


class HealthService:
    def __init__(
        self,
        settings: Settings,
        store: SqliteStateStore,
        runtime_jobs: Any,
        model_service: Any,
        dataset_service: Any,
    ) -> None:
        self.settings = settings
        self.store = store
        self.runtime_jobs = runtime_jobs
        self.model_service = model_service
        self.dataset_service = dataset_service

    # -- liveness / readiness ------------------------------------------------

    def liveness(self) -> dict[str, Any]:
        return {"status": "ok", "time": utc_now()}

    def readiness(self) -> dict[str, Any]:
        checks = {
            "db": self._check_db(),
            "disk": self._check_disk(),
            "state_dirs": self._check_state_dirs(),
        }
        ok = all(bool(check.get("ok")) for check in checks.values())
        return {"status": "ready" if ok else "not_ready", "checks": checks}

    # -- deep checks ---------------------------------------------------------

    def dependencies(self) -> dict[str, Any]:
        checks = {
            "db": self._check_db(),
            "executor": self._check_executor(),
            "disk": self._check_disk(),
            "state_dirs": self._check_state_dirs(),
        }
        ok = all(bool(check.get("ok")) for check in checks.values())
        return {"status": "ok" if ok else "degraded", "checks": checks}

    def model(self) -> dict[str, Any]:
        current = self.model_service.current()
        published = current is not None
        return {
            "status": "ok" if published else "unavailable",
            "published": published,
            "current": current,
        }

    def data(self) -> dict[str, Any]:
        freshness = self.dataset_service.freshness_summary()
        return {
            "status": "stale" if freshness.get("is_stale") else "ok",
            **freshness,
        }

    # -- individual checks ---------------------------------------------------

    def _check_db(self) -> dict[str, Any]:
        try:
            self.store.list(JOBS_TABLE, limit=1)
            writable = _dir_writable(self.settings.state_root)
            return {
                "ok": True,
                "writable": writable,
                "detail": "state store readable",
            }
        except Exception as exc:  # noqa: BLE001 — report, never raise
            return {"ok": False, "detail": str(exc)}

    def _check_executor(self) -> dict[str, Any]:
        writable = _dir_writable(self.settings.job_runs_root)
        return {
            "ok": writable,
            "writable": writable,
            "python": sys.executable,
            "max_concurrent_jobs": int(self.settings.max_concurrent_jobs),
        }

    def _check_disk(self) -> dict[str, Any]:
        free = _free_disk_bytes(self.settings.state_root)
        ok = free < 0 or free >= int(self.settings.min_free_disk_bytes)
        return {
            "ok": ok,
            "free_bytes": free,
            "min_free_bytes": int(self.settings.min_free_disk_bytes),
        }

    def _check_state_dirs(self) -> dict[str, Any]:
        dirs = {
            "state_root": self.settings.state_root,
            "report_root": self.settings.report_root,
            "job_logs_root": self.settings.job_logs_root,
            "job_runs_root": self.settings.job_runs_root,
        }
        missing = [name for name, path in dirs.items() if not _dir_writable(path)]
        return {"ok": not missing, "missing": missing}
