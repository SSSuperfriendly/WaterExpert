from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a WaterExpert Software prediction job.")
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--artifact-root", required=True)
    return parser.parse_args()


def update_status(status_file: Path, **updates: Any) -> dict[str, Any]:
    current: dict[str, Any] = {}
    if status_file.exists():
        try:
            current = json.loads(status_file.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    current.update(updates)
    atomic_write_json(status_file, current)
    return current


def run_step(
    command: list[str],
    cwd: Path,
    status_file: Path,
    step_name: str,
) -> None:
    update_status(
        status_file,
        status="running",
        stage=step_name,
        updated_at=utc_now(),
        message=f"Running {step_name}.",
    )
    completed = subprocess.run(command, cwd=str(cwd), check=False)
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            returncode=completed.returncode,
            cmd=command,
        )


def verify_required_outputs(output_root: Path) -> None:
    required = [
        output_root / "agent" / "agent_context.json",
        output_root / "agent" / "scenario_triage.json",
        output_root / "agent" / "response_playbook.json",
        output_root / "predictions" / "predictions.csv",
        output_root / "metrics" / "metrics.json",
        output_root / "thresholds" / "cmfbe_threshold_summary.csv",
        output_root / "thresholds" / "cmfbe_thresholds_by_context.csv",
        output_root / "thresholds" / "mechanism_parameter_threshold_kg.json",
        output_root / "sensitivity" / "cmfbe_sobol_indices.json",
        output_root / "counterfactual" / "cmfbe_counterfactual_summary.csv",
        output_root / "counterfactual" / "cmfbe_joint_counterfactual_summary.csv",
        output_root / "boundary" / "boundary_detection_summary.json",
        output_root / "boundary" / "boundary_label_generation_summary.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Job-scoped artifact chain is incomplete: " + ", ".join(missing)
        )


def main() -> int:
    args = parse_args()
    runtime_root = Path(args.runtime_root).resolve()
    config_path = Path(args.config).resolve()
    status_file = Path(args.status_file).resolve()
    artifact_root = Path(args.artifact_root).resolve()
    pipeline_path = runtime_root / "scripts" / "run_full_pipeline.py"
    post_steps = [
        (
            "threshold-analysis",
            [
                sys.executable,
                str(runtime_root / "scripts" / "analyze_cmfbe_thresholds.py"),
                "--output-root",
                str(artifact_root),
            ],
        ),
        (
            "threshold-knowledge-graph",
            [
                sys.executable,
                str(runtime_root / "scripts" / "export_threshold_knowledge_graph.py"),
                "--output-root",
                str(artifact_root),
            ],
        ),
        (
            "sobol-counterfactual",
            [
                sys.executable,
                str(runtime_root / "scripts" / "analyze_cmfbe_sobol_counterfactual.py"),
                "--output-root",
                str(artifact_root),
            ],
        ),
        (
            "agent-context-export",
            [
                sys.executable,
                str(runtime_root / "scripts" / "export_agent_context.py"),
                "--output-root",
                str(artifact_root),
            ],
        ),
    ]

    atomic_write_json(
        status_file,
        {
            "status": "running",
            "started_at": utc_now(),
            "runtime_root": str(runtime_root),
            "config_path": str(config_path),
            "pipeline_path": str(pipeline_path),
            "artifact_root": str(artifact_root),
            "stage": "pipeline",
            "message": "Running full pipeline.",
        },
    )

    try:
        run_step(
            [sys.executable, str(pipeline_path), "--config", str(config_path)],
            cwd=runtime_root,
            status_file=status_file,
            step_name="pipeline",
        )
        for step_name, command in post_steps:
            run_step(
                command,
                cwd=runtime_root,
                status_file=status_file,
                step_name=step_name,
            )
        update_status(
            status_file,
            stage="artifact-validation",
            updated_at=utc_now(),
            message="Validating job-scoped artifact chain.",
        )
        verify_required_outputs(artifact_root)
        atomic_write_json(
            status_file,
            {
                "status": "completed",
                "started_at": json.loads(status_file.read_text(encoding="utf-8")).get("started_at"),
                "finished_at": utc_now(),
                "runtime_root": str(runtime_root),
                "config_path": str(config_path),
                "pipeline_path": str(pipeline_path),
                "artifact_root": str(artifact_root),
                "stage": "completed",
                "return_code": 0,
                "message": "Job completed with verified job-scoped artifacts.",
            },
        )
        return 0
    except Exception as exc:
        return_code = (
            int(exc.returncode)
            if isinstance(exc, subprocess.CalledProcessError)
            else -1
        )
        atomic_write_json(
            status_file,
            {
                "status": "failed",
                "started_at": json.loads(status_file.read_text(encoding="utf-8")).get("started_at"),
                "finished_at": utc_now(),
                "runtime_root": str(runtime_root),
                "config_path": str(config_path),
                "pipeline_path": str(pipeline_path),
                "artifact_root": str(artifact_root),
                "return_code": return_code,
                "message": "Job failed during pipeline orchestration.",
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
