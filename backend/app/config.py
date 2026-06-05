from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT
VAR_ROOT_NAME = "var"
STATE_ROOT_NAME = "state"
REPORT_ROOT_NAME = "reports"


@dataclass(frozen=True)
class Settings:
    app_name: str
    project_root: Path
    runtime_root: Path
    frontend_root: Path
    report_root: Path
    state_root: Path

    @property
    def outputs_root(self) -> Path:
        return self.runtime_root / "outputs"

    @property
    def default_config_path(self) -> Path:
        return self.runtime_root / "configs" / "prototype_repo.yaml"

    @property
    def imports_root(self) -> Path:
        return self.runtime_root / "data" / "imports"

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
        frontend_root=(PROJECT_ROOT / "frontend").resolve(),
        report_root=(PROJECT_ROOT / VAR_ROOT_NAME / REPORT_ROOT_NAME).resolve(),
        state_root=(PROJECT_ROOT / VAR_ROOT_NAME / STATE_ROOT_NAME).resolve(),
    )
