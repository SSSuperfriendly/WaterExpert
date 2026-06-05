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
    parser = argparse.ArgumentParser(description="Run a WaterTurbiditySoftware prediction job.")
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--status-file", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime_root = Path(args.runtime_root).resolve()
    config_path = Path(args.config).resolve()
    status_file = Path(args.status_file).resolve()
    pipeline_path = runtime_root / "scripts" / "run_full_pipeline.py"

    atomic_write_json(
        status_file,
        {
            "status": "running",
            "started_at": utc_now(),
            "runtime_root": str(runtime_root),
            "config_path": str(config_path),
            "pipeline_path": str(pipeline_path),
        },
    )

    try:
        completed = subprocess.run(
            [sys.executable, str(pipeline_path), "--config", str(config_path)],
            cwd=str(runtime_root),
            check=False,
        )
        final_status = "completed" if completed.returncode == 0 else "failed"
        atomic_write_json(
            status_file,
            {
                "status": final_status,
                "started_at": json.loads(status_file.read_text(encoding="utf-8")).get("started_at"),
                "finished_at": utc_now(),
                "runtime_root": str(runtime_root),
                "config_path": str(config_path),
                "pipeline_path": str(pipeline_path),
                "return_code": int(completed.returncode),
            },
        )
        return int(completed.returncode)
    except Exception as exc:
        atomic_write_json(
            status_file,
            {
                "status": "failed",
                "started_at": json.loads(status_file.read_text(encoding="utf-8")).get("started_at"),
                "finished_at": utc_now(),
                "runtime_root": str(runtime_root),
                "config_path": str(config_path),
                "pipeline_path": str(pipeline_path),
                "return_code": -1,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
