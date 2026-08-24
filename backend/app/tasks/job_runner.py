from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNNING_STATUS = "running"
COMPLETED_STATUS = "completed"
FAILED_STATUS = "failed"
PIPELINE_SCRIPT = Path("scripts") / "pipeline" / "run_full_pipeline.py"
THRESHOLD_ANALYSIS_SCRIPT = Path("scripts") / "analysis" / "analyze_cmfbe_thresholds.py"
THRESHOLD_KG_SCRIPT = Path("scripts") / "exports" / "export_threshold_knowledge_graph.py"
SOBOL_COUNTERFACTUAL_SCRIPT = Path("scripts") / "analysis" / "analyze_cmfbe_sobol_counterfactual.py"
AGENT_CONTEXT_SCRIPT = Path("scripts") / "exports" / "export_agent_context.py"


@dataclass(frozen=True)
class JobRunnerArgs:
    runtime_root: Path
    config_path: Path
    status_file: Path
    artifact_root: Path


@dataclass(frozen=True)
class StepSpec:
    name: str
    command: list[str]


REQUIRED_OUTPUTS: tuple[str, ...] = (
    "agent/agent_context.json",
    "agent/scenario_triage.json",
    "agent/response_playbook.json",
    "predictions/predictions.csv",
    "metrics/metrics.json",
    "thresholds/cmfbe_threshold_summary.csv",
    "thresholds/cmfbe_thresholds_by_context.csv",
    "thresholds/mechanism_parameter_threshold_kg.json",
    "sensitivity/cmfbe_sobol_indices.json",
    "counterfactual/cmfbe_counterfactual_summary.csv",
    "counterfactual/cmfbe_joint_counterfactual_summary.csv",
    "boundary/boundary_detection_summary.json",
    "boundary/boundary_label_generation_summary.json",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def parse_args() -> JobRunnerArgs:
    parser = argparse.ArgumentParser(description="Run a WaterExpert Software prediction job.")
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--artifact-root", required=True)
    parsed = parser.parse_args()
    return JobRunnerArgs(
        runtime_root=Path(parsed.runtime_root).resolve(),
        config_path=Path(parsed.config).resolve(),
        status_file=Path(parsed.status_file).resolve(),
        artifact_root=Path(parsed.artifact_root).resolve(),
    )


def read_status(status_file: Path) -> dict[str, Any]:
    if not status_file.exists():
        return {}
    try:
        return json.loads(status_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_status(status_file: Path, payload: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(status_file, payload)
    return payload


def update_status(status_file: Path, **updates: Any) -> dict[str, Any]:
    current = read_status(status_file)
    current.update(updates)
    return write_status(status_file, current)


def pipeline_path(runtime_root: Path) -> Path:
    return runtime_root / PIPELINE_SCRIPT


def post_process_steps(runtime_root: Path, artifact_root: Path) -> list[StepSpec]:
    return [
        StepSpec(
            name="threshold-analysis",
            command=[
                sys.executable,
                str(runtime_root / THRESHOLD_ANALYSIS_SCRIPT),
                "--output-root",
                str(artifact_root),
            ],
        ),
        StepSpec(
            name="threshold-knowledge-graph",
            command=[
                sys.executable,
                str(runtime_root / THRESHOLD_KG_SCRIPT),
                "--output-root",
                str(artifact_root),
            ],
        ),
        StepSpec(
            name="sobol-counterfactual",
            command=[
                sys.executable,
                str(runtime_root / SOBOL_COUNTERFACTUAL_SCRIPT),
                "--output-root",
                str(artifact_root),
            ],
        ),
        StepSpec(
            name="agent-context-export",
            command=[
                sys.executable,
                str(runtime_root / AGENT_CONTEXT_SCRIPT),
                "--output-root",
                str(artifact_root),
            ],
        ),
    ]


def initialize_status(args: JobRunnerArgs) -> None:
    write_status(
        args.status_file,
        {
            "status": RUNNING_STATUS,
            "started_at": utc_now(),
            "runtime_root": str(args.runtime_root),
            "config_path": str(args.config_path),
            "pipeline_path": str(pipeline_path(args.runtime_root)),
            "artifact_root": str(args.artifact_root),
            "stage": "pipeline",
            "message": "Running full pipeline.",
        },
    )


def run_step(step: StepSpec, *, cwd: Path, status_file: Path) -> None:
    update_status(
        status_file,
        status=RUNNING_STATUS,
        stage=step.name,
        updated_at=utc_now(),
        message=f"Running {step.name}.",
    )
    completed = subprocess.run(step.command, cwd=str(cwd), check=False)
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            returncode=completed.returncode,
            cmd=step.command,
        )


def verify_required_outputs(artifact_root: Path) -> None:
    missing = [
        str(artifact_root / relative_path)
        for relative_path in REQUIRED_OUTPUTS
        if not (artifact_root / relative_path).exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Job-scoped artifact chain is incomplete: " + ", ".join(missing)
        )


def complete_status(args: JobRunnerArgs) -> None:
    started_at = read_status(args.status_file).get("started_at")
    write_status(
        args.status_file,
        {
            "status": COMPLETED_STATUS,
            "started_at": started_at,
            "finished_at": utc_now(),
            "runtime_root": str(args.runtime_root),
            "config_path": str(args.config_path),
            "pipeline_path": str(pipeline_path(args.runtime_root)),
            "artifact_root": str(args.artifact_root),
            "stage": COMPLETED_STATUS,
            "return_code": 0,
            "message": "Job completed with verified job-scoped artifacts.",
        },
    )


def fail_status(args: JobRunnerArgs, exc: Exception) -> None:
    started_at = read_status(args.status_file).get("started_at")
    return_code = (
        int(exc.returncode)
        if isinstance(exc, subprocess.CalledProcessError)
        else -1
    )
    write_status(
        args.status_file,
        {
            "status": FAILED_STATUS,
            "started_at": started_at,
            "finished_at": utc_now(),
            "runtime_root": str(args.runtime_root),
            "config_path": str(args.config_path),
            "pipeline_path": str(pipeline_path(args.runtime_root)),
            "artifact_root": str(args.artifact_root),
            "return_code": return_code,
            "message": "Job failed during pipeline orchestration.",
            "error": f"{type(exc).__name__}: {exc}",
        },
    )


def main() -> int:
    args = parse_args()
    initialize_status(args)
    try:
        run_step(
            StepSpec(
                name="pipeline",
                command=[sys.executable, str(pipeline_path(args.runtime_root)), "--config", str(args.config_path)],
            ),
            cwd=args.runtime_root,
            status_file=args.status_file,
        )
        for step in post_process_steps(args.runtime_root, args.artifact_root):
            run_step(step, cwd=args.runtime_root, status_file=args.status_file)
        update_status(
            args.status_file,
            stage="artifact-validation",
            updated_at=utc_now(),
            message="Validating job-scoped artifact chain.",
        )
        verify_required_outputs(args.artifact_root)
        complete_status(args)
        return 0
    except Exception as exc:
        fail_status(args, exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
