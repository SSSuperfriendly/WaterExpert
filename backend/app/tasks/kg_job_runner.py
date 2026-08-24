"""Background subprocess that builds the literature knowledge graph.

Self-contained counterpart to ``job_runner.py`` (which is tied to the
prediction pipeline). Launched by ``KnowledgeGraphService.start_build`` via
``python -m backend.app.tasks.kg_job_runner``. The runner reads cleaned TXT
files, chunks them, asks the LLM to extract entity/relation triples per chunk,
and writes ``entities.csv`` / ``relations.csv`` / ``graph.json`` into the KG
directory, updating a JSON status file as it progresses.

The LLM loop is the slow, network-bound part of the pipeline, which is why it
runs out-of-band rather than inside a request handler.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services.kg_service import extract_triples, save_kg, split_text

RUNNING_STATUS = "running"
COMPLETED_STATUS = "completed"
FAILED_STATUS = "failed"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class KgJobRunnerArgs:
    kg_dir: Path
    text_dir: Path
    status_file: Path
    selected_files: list[str]
    max_chars: int


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
    except Exception:
        return {}


def write_status(status_file: Path, payload: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(status_file, payload)
    return payload


def update_status(status_file: Path, **updates: Any) -> dict[str, Any]:
    current = read_status(status_file)
    current.update(updates)
    return write_status(status_file, current)


def parse_args() -> KgJobRunnerArgs:
    parser = argparse.ArgumentParser(description="Build the literature knowledge graph.")
    parser.add_argument("--kg-dir", required=True)
    parser.add_argument("--text-dir", required=True)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--selected-files", required=True)
    parser.add_argument("--max-chars", type=int, default=1200)
    parsed = parser.parse_args()

    try:
        selected_files = json.loads(parsed.selected_files)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid --selected-files JSON: {exc}") from exc

    if not isinstance(selected_files, list):
        raise ValueError("--selected-files must decode to a JSON array.")

    return KgJobRunnerArgs(
        kg_dir=Path(parsed.kg_dir).resolve(),
        text_dir=Path(parsed.text_dir).resolve(),
        status_file=Path(parsed.status_file).resolve(),
        selected_files=[str(name) for name in selected_files],
        max_chars=int(parsed.max_chars),
    )


def initialize_status(args: KgJobRunnerArgs) -> None:
    write_status(
        args.status_file,
        {
            "status": RUNNING_STATUS,
            "started_at": utc_now(),
            "progress": 0,
            "message": "正在准备文本块。",
        },
    )


def load_chunks(args: KgJobRunnerArgs) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    for name in args.selected_files:
        path = args.text_dir / name
        if not path.exists():
            raise FileNotFoundError(f"文本文件不存在: {name}")
        text = path.read_text(encoding="utf-8", errors="ignore")
        for chunk in split_text(text, max_chars=args.max_chars):
            chunks.append((name, chunk))
    return chunks


def main() -> int:
    args = parse_args()
    initialize_status(args)

    try:
        chunks = load_chunks(args)
        total = len(chunks)

        if total == 0:
            update_status(
                args.status_file,
                progress=100,
                message="所选文本没有可抽取的内容。",
            )

        all_triples = []

        for index, (filename, chunk) in enumerate(chunks, start=1):
            update_status(
                args.status_file,
                status=RUNNING_STATUS,
                progress=int((index - 1) / max(total, 1) * 100),
                current_file=filename,
                message=f"正在抽取：{filename}（第 {index}/{total} 块）。",
            )

            triples = extract_triples(chunk)
            for triple in triples:
                triple["source_file"] = filename
                all_triples.append(triple)

        relation_count = save_kg(all_triples, args.kg_dir)

        started_at = read_status(args.status_file).get("started_at")
        write_status(
            args.status_file,
            {
                "status": COMPLETED_STATUS,
                "started_at": started_at,
                "finished_at": utc_now(),
                "progress": 100,
                "relation_count": relation_count,
                "return_code": 0,
                "message": f"知识图谱构建完成，共抽取关系 {relation_count} 条。",
            },
        )
        return 0
    except Exception as exc:
        started_at = read_status(args.status_file).get("started_at")
        write_status(
            args.status_file,
            {
                "status": FAILED_STATUS,
                "started_at": started_at,
                "finished_at": utc_now(),
                "return_code": -1,
                "message": "知识图谱构建失败。",
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
