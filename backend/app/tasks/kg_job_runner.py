"""Background subprocess that builds the literature knowledge graph.

Self-contained counterpart to ``job_runner.py`` (which is tied to the
prediction pipeline). Launched by ``KnowledgeGraphService.start_build`` via
``python -m backend.app.tasks.kg_job_runner``. The runner reads cleaned TXT
files, chunks them, asks the LLM to extract entity/relation triples per chunk,
and writes ``entities.csv`` / ``relations.csv`` / ``graph.json`` into the KG
directory, updating a JSON status file as it progresses.

It then partitions the finished graph into communities and writes
``communities.json`` — and, when an LLM is configured, ``summaries.json``. That
second phase exists so that no question ever pays for it: a summary generated
inside a request handler would be a metered API call on the critical path. It
is bounded by ``community_max_llm_calls`` per rebuild, and every failure in it
is absorbed, because a graph without communities is still a usable graph.

The LLM loop is the slow, network-bound part of the pipeline, which is why it
runs out-of-band rather than inside a request handler.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services.kg_service import extract_triples, save_kg, split_text_with_spans

RUNNING_STATUS = "running"
COMPLETED_STATUS = "completed"
FAILED_STATUS = "failed"

#: Progress the extraction loop is allowed to reach. The remaining tenth is the
#: community phase, which is fast in wall-clock terms but is the only other
#: thing that happens, and which the panel should be able to show.
EXTRACTION_CEILING = 90

logger = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class KgJobRunnerArgs:
    kg_dir: Path
    text_dir: Path
    status_file: Path
    selected_files: list[str]
    max_chars: int


@dataclass(frozen=True)
class TextChunk:
    """One chunk of source text, addressable by a stable id.

    ``chunk_id`` is ``f"{stem}#{ordinal:04d}"`` — deterministic across rebuilds
    of the same file, and human-readable enough to appear in a citation. The
    ordinal is per source file, so ``clean_a (4)#0007`` means the eighth chunk
    of ``clean_a (4).txt``.
    """

    chunk_id: str
    source_file: str
    ordinal: int
    char_start: int
    char_end: int
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_file": self.source_file,
            "ordinal": self.ordinal,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "text": self.text,
        }


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
    except Exception:  # noqa: BLE001 — a corrupt/partial status file is treated as "no status yet"
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
        raise TypeError("--selected-files must decode to a JSON array.")

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


def load_chunks(args: KgJobRunnerArgs) -> list[TextChunk]:
    """Read the selected files and chunk them into citable records.

    Uses :func:`split_text_with_spans` rather than ``split_text`` because the
    offsets are what let a citation point back into the source text, and that is
    the whole reason ``chunks.jsonl`` is written at all.
    """
    chunks: list[TextChunk] = []
    for name in args.selected_files:
        path = args.text_dir / name
        if not path.exists():
            raise FileNotFoundError(f"文本文件不存在: {name}")
        text = path.read_text(encoding="utf-8", errors="ignore")
        stem = Path(name).stem
        for ordinal, (start, end, chunk_text) in enumerate(
            split_text_with_spans(text, max_chars=args.max_chars)
        ):
            chunks.append(
                TextChunk(
                    chunk_id=f"{stem}#{ordinal:04d}",
                    source_file=name,
                    ordinal=ordinal,
                    char_start=start,
                    char_end=end,
                    text=chunk_text,
                )
            )
    return chunks


def build_communities(args: KgJobRunnerArgs) -> int:
    """Partition the freshly written graph and materialise its communities.

    Returns the number of communities written, or ``0`` when the phase is
    disabled, the graph is unreadable, or anything else goes wrong. There is no
    exception path out of here on purpose: ``relations.csv`` is already on disk
    and correct by this point, so a community failure must not turn a successful
    build into a failed one. A graph with no communities is still answerable —
    the router just stays local.
    """
    from backend.app.services import kg_llm
    from backend.app.services.graph_rag.config import GraphRagConfig
    from backend.app.services.graph_rag.global_search import materialise_source_communities
    from backend.app.services.graph_rag.sources import load_platform_source

    config = GraphRagConfig.from_env()
    if not config.communities_enabled:
        return 0

    # ``runtime_dir`` only: the runner is writing the runtime graph, and falling
    # back to the committed baseline here would partition the shipped sample
    # instead of the thing that was just built.
    source = load_platform_source(args.kg_dir, None)
    if source is None:
        return 0

    # The hash ``save_kg`` computed for this build, taken from the file it wrote
    # rather than recomputed — a cached summary is only usable while this value
    # still matches, and two code paths deriving it is one path too many.
    index_path = args.kg_dir / "kg_index.json"
    content_hash_value = ""
    if index_path.exists():
        try:
            content_hash_value = str(json.loads(index_path.read_text(encoding="utf-8")).get("content_hash") or "")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            content_hash_value = ""

    def on_progress(done: int, total: int, community_id: str) -> None:
        update_status(
            args.status_file,
            status=RUNNING_STATUS,
            progress=EXTRACTION_CEILING + int(done / max(total, 1) * (100 - EXTRACTION_CEILING)),
            message=f"正在生成社区摘要（{done}/{total}）。",
        )

    call_llm = kg_llm.call_llm if (config.summaries_enabled and kg_llm.is_llm_configured()) else None
    communities = materialise_source_communities(
        source,
        config,
        args.kg_dir,
        content_hash_value=content_hash_value,
        call_llm=call_llm,
        on_progress=on_progress,
    )
    return len(communities)


def main() -> int:
    args = parse_args()
    initialize_status(args)

    try:
        chunks = load_chunks(args)
        total = len(chunks)

        if total == 0:
            update_status(
                args.status_file,
                progress=EXTRACTION_CEILING,
                message="所选文本没有可抽取的内容。",
            )

        all_triples = []

        for index, chunk in enumerate(chunks, start=1):
            update_status(
                args.status_file,
                status=RUNNING_STATUS,
                progress=int((index - 1) / max(total, 1) * EXTRACTION_CEILING),
                current_file=chunk.source_file,
                message=f"正在抽取：{chunk.source_file}（第 {index}/{total} 块）。",
            )

            triples = extract_triples(chunk.text)
            for triple in triples:
                triple["source_file"] = chunk.source_file
                # Provenance the dedupe in save_kg would otherwise destroy:
                # which chunk each surviving relation was found in. Stripped
                # from relations.csv, kept in occurrences.jsonl.
                triple["chunk_id"] = chunk.chunk_id
                triple["ordinal"] = chunk.ordinal
                all_triples.append(triple)

        relation_count = save_kg(
            all_triples,
            args.kg_dir,
            chunks=[chunk.as_dict() for chunk in chunks],
        )

        update_status(
            args.status_file,
            status=RUNNING_STATUS,
            progress=EXTRACTION_CEILING,
            message="正在构建社区结构。",
        )
        try:
            community_count = build_communities(args)
        except Exception as exc:  # noqa: BLE001 — communities are an enhancement, and the build is already saved
            logger.warning("Community phase failed: %s", exc)
            community_count = 0

        message = f"知识图谱构建完成，共抽取关系 {relation_count} 条。"
        if community_count:
            message = f"知识图谱构建完成，共抽取关系 {relation_count} 条、社区 {community_count} 个。"

        started_at = read_status(args.status_file).get("started_at")
        write_status(
            args.status_file,
            {
                "status": COMPLETED_STATUS,
                "started_at": started_at,
                "finished_at": utc_now(),
                "progress": 100,
                "relation_count": relation_count,
                "community_count": community_count,
                "return_code": 0,
                "message": message,
            },
        )
        return 0
    except Exception as exc:  # noqa: BLE001 — the job boundary always writes a FAILED status instead of crashing the runner
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
