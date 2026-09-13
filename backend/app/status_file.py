"""Shared job status-file helpers for the background task runners.

A status file is a small JSON object a subprocess rewrites atomically as it
progresses; a reader that catches a half-written file as "no status yet" is what
lets the API poll it while the writer is live.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def read_status(status_file: Path) -> dict[str, Any]:
    if not status_file.exists():
        return {}
    try:
        return json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        # A corrupt or partially written status file means "no status yet".
        return {}


def write_status(status_file: Path, payload: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(status_file, payload)
    return payload


def update_status(status_file: Path, **updates: Any) -> dict[str, Any]:
    current = read_status(status_file)
    current.update(updates)
    return write_status(status_file, current)
