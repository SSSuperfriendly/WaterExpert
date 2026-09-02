from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT
VAR_ROOT_NAME = "var"
STATE_ROOT_NAME = "state"
REPORT_ROOT_NAME = "reports"

#: Upload guards (review item 7). 512 MB is generous for a daily-granularity CSV
#: and small enough that a single request cannot exhaust the disk.
DEFAULT_MAX_UPLOAD_BYTES = 512 * 1024 * 1024
#: An archive that expands beyond this ratio is treated as a compression bomb.
DEFAULT_MAX_COMPRESSION_RATIO = 120.0

#: Task centre defaults (review item 10).
DEFAULT_MAX_CONCURRENT_JOBS = 2
DEFAULT_JOB_TIMEOUT_SECONDS = 6 * 60 * 60

#: Data lifecycle defaults (review item 26). ``0`` disables a retention rule.
DEFAULT_JOB_RUN_RETENTION_DAYS = 30
DEFAULT_REPORT_RETENTION_DAYS = 365
DEFAULT_UPLOAD_RETENTION_DAYS = 180
#: Free-space floor below which readiness fails and a capacity alert fires.
DEFAULT_MIN_FREE_DISK_BYTES = 2 * 1024 * 1024 * 1024


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str
    project_root: Path
    runtime_root: Path
    frontend_root: Path
    report_root: Path
    state_root: Path

    # -- security -----------------------------------------------------------
    #: CORS allow-list. ``allow_origins=["*"]`` with credentials was flagged in
    #: review item 7; the default here is same-origin plus the local dev server.
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    cors_allow_credentials: bool = True
    #: When false, ``/api/v1/auth/hint`` returns nothing instead of demo creds.
    expose_demo_hint: bool = False
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO

    # -- task centre --------------------------------------------------------
    max_concurrent_jobs: int = DEFAULT_MAX_CONCURRENT_JOBS
    job_timeout_seconds: int = DEFAULT_JOB_TIMEOUT_SECONDS

    # -- lifecycle ----------------------------------------------------------
    job_run_retention_days: int = DEFAULT_JOB_RUN_RETENTION_DAYS
    report_retention_days: int = DEFAULT_REPORT_RETENTION_DAYS
    upload_retention_days: int = DEFAULT_UPLOAD_RETENTION_DAYS
    min_free_disk_bytes: int = DEFAULT_MIN_FREE_DISK_BYTES

    # -- notifications ------------------------------------------------------
    #: Generic webhook for event notifications (WeCom / DingTalk / Slack style).
    notification_webhook_url: str = ""

    # -- external agent -----------------------------------------------------
    #: Base URL of the externally deployed WaterExpert agent API
    #: (docs/internal/INTEGRATION_GUIDE.md). Empty string keeps the platform
    #: self-contained and surfaces ``agent_unavailable`` until configured.
    agent_api_url: str = ""
    #: Per-request timeout for calls out to the deployed agent API.
    agent_api_timeout_seconds: float = 30.0

    data_freshness_warning_days: int = 7

    @property
    def outputs_root(self) -> Path:
        return self.runtime_root / "outputs"

    @property
    def default_config_path(self) -> Path:
        return self.runtime_root / "configs" / "default.yaml"

    @property
    def imports_root(self) -> Path:
        return self.runtime_root / "data" / "imports"

    @property
    def managed_import_root(self) -> Path:
        """The only directory a server-side path import may read from.

        Review item 7: ``/api/v1/data/import`` previously accepted any path the
        server process could reach.
        """
        return self.runtime_root / "data" / "inbox"

    @property
    def datasets_root(self) -> Path:
        """Canonicalized, graded dataset versions produced by the ingestion chain."""
        return self.var_root / "datasets"

    @property
    def cases_root(self) -> Path:
        return self.var_root / "cases"

    @property
    def job_logs_root(self) -> Path:
        return self.state_root / "job_logs"

    @property
    def job_runs_root(self) -> Path:
        return self.state_root / "job_runs"

    @property
    def state_db_path(self) -> Path:
        return self.state_root / "app_state.sqlite3"

    @property
    def var_root(self) -> Path:
        return self.project_root / VAR_ROOT_NAME

    @property
    def kg_root(self) -> Path:
        return self.var_root / "knowledge_graph"


def get_settings() -> Settings:
    runtime_root = Path(
        os.environ.get(
            "WATEREXPERT_RUNTIME_ROOT",
            os.environ.get("WATERTURBIDITY_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT)),
        )
    ).resolve()
    return Settings(
        app_name="WaterExpert Software",
        project_root=PROJECT_ROOT,
        runtime_root=runtime_root,
        frontend_root=(PROJECT_ROOT / "frontend" / "out").resolve(),
        report_root=(PROJECT_ROOT / VAR_ROOT_NAME / REPORT_ROOT_NAME).resolve(),
        state_root=(PROJECT_ROOT / VAR_ROOT_NAME / STATE_ROOT_NAME).resolve(),
        cors_origins=_env_list(
            "WATEREXPERT_CORS_ORIGINS",
            ("http://localhost:3000", "http://127.0.0.1:3000"),
        ),
        cors_allow_credentials=_env_bool("WATEREXPERT_CORS_ALLOW_CREDENTIALS", True),
        expose_demo_hint=_env_bool("WATEREXPERT_ENABLE_DEMO_HINT", False),
        max_upload_bytes=_env_int("WATEREXPERT_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES),
        max_compression_ratio=_env_float(
            "WATEREXPERT_MAX_COMPRESSION_RATIO", DEFAULT_MAX_COMPRESSION_RATIO
        ),
        max_concurrent_jobs=_env_int(
            "WATEREXPERT_MAX_CONCURRENT_JOBS", DEFAULT_MAX_CONCURRENT_JOBS
        ),
        job_timeout_seconds=_env_int(
            "WATEREXPERT_JOB_TIMEOUT_SECONDS", DEFAULT_JOB_TIMEOUT_SECONDS
        ),
        job_run_retention_days=_env_int(
            "WATEREXPERT_JOB_RUN_RETENTION_DAYS", DEFAULT_JOB_RUN_RETENTION_DAYS
        ),
        report_retention_days=_env_int(
            "WATEREXPERT_REPORT_RETENTION_DAYS", DEFAULT_REPORT_RETENTION_DAYS
        ),
        upload_retention_days=_env_int(
            "WATEREXPERT_UPLOAD_RETENTION_DAYS", DEFAULT_UPLOAD_RETENTION_DAYS
        ),
        min_free_disk_bytes=_env_int(
            "WATEREXPERT_MIN_FREE_DISK_BYTES", DEFAULT_MIN_FREE_DISK_BYTES
        ),
        notification_webhook_url=os.environ.get("WATEREXPERT_NOTIFICATION_WEBHOOK", "").strip(),
        data_freshness_warning_days=_env_int("WATEREXPERT_DATA_FRESHNESS_WARNING_DAYS", 7),
        agent_api_url=os.environ.get(
            "WATEREXPERT_AGENT_API_URL", "http://219.228.144.101:8000/api"
        ).strip(),
        agent_api_timeout_seconds=_env_float(
            "WATEREXPERT_AGENT_API_TIMEOUT_SECONDS", 30.0
        ),
    )
