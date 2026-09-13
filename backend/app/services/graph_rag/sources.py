"""Loaders that turn each on-disk graph into a :class:`GraphSource`.

Both loaders namespace node keys with the source id, so ``platform::浊度`` and
``inherited::TURBIDITY`` can never be confused for one another, and neither can
a future third source collide with either.

The inherited loader deserves a note. ``create_final_relationships.parquet`` is
a Microsoft GraphRAG export whose columns are
``source, target, weight, description, text_unit_ids, id, human_readable_id,
source_degree, target_degree, rank``. There is **no relation-type column** —
``description`` is the relation, and it is Chinese while the entity names are
English. The mapping below normalises that onto the platform's field names so
every downstream consumer has exactly one code path:

===================  ==================================================
platform             inherited
===================  ==================================================
``source``/``target``  English entity names, as-is
``relation``           ``""`` — rendered as ``--(description)-->``
``evidence``           ``description`` (Chinese; the lexical mainstay)
``weight``/``rank``    taken from GraphRAG rather than recomputed
``source_degree``      taken from GraphRAG
``source_file``        the parquet's filename
``chunk_id``           ``None`` — no ``text_units`` file was exported
===================  ==================================================
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.index import (
    GraphSource,
    Relation,
    build_graph,
    node_key,
    read_chunks,
    read_occurrences,
)

logger = logging.getLogger(__name__)

PLATFORM_SOURCE_ID = "platform"
INHERITED_SOURCE_ID = "inherited"

PLATFORM_RELATIONS_FILE = "relations.csv"
INHERITED_RELATIONS_FILE = "create_final_relationships.parquet"

#: Where the inherited parquet lives, in preference order. It is a registered
#: dataset (``data/dataset_registry.json``), so the versioned dataset path is
#: checked first and the raw repo copy is only a fallback.
INHERITED_RELATIVE_PATHS: tuple[str, ...] = (
    "var/datasets/kg_relationships/v1/raw/create_final_relationships.parquet",
    "data/knowledge_graph/create_final_relationships.parquet",
)


def _normalise_key(key: Any) -> str:
    return " ".join(str(key or "").split())


def load_platform_source(
    runtime_dir: Path | None,
    baseline_dir: Path | None,
) -> GraphSource | None:
    """The user's own graph: runtime if built, otherwise the committed baseline.

    Runtime wins outright rather than being merged with the baseline — the
    baseline is a shipped fallback, and merging would duplicate near-identical
    edges and double-count them in every ranking.
    """
    for directory, source, label, label_key in (
        (runtime_dir, "runtime", "运行时图谱", "kg.source.runtime"),
        (baseline_dir, "baseline", "基线图谱", "kg.source.baseline"),
    ):
        if directory is None:
            continue
        relations_path = directory / PLATFORM_RELATIONS_FILE
        if not relations_path.exists():
            continue
        source_obj = _load_platform_relations(relations_path)
        if source_obj is None:
            continue
        source_obj.provenance = f"{source}:{relations_path}"
        source_obj.label = label
        source_obj.label_key = label_key
        source_obj.chunks = read_chunks(directory / "chunks.jsonl")
        source_obj.occurrences = _namespace_occurrences(
            read_occurrences(directory / "occurrences.jsonl"),
            PLATFORM_SOURCE_ID,
        )
        return source_obj
    return None


def _load_platform_relations(relations_path: Path) -> GraphSource | None:
    try:
        frame = pd.read_csv(relations_path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        frame = pd.read_csv(relations_path, encoding="utf-8")
    except (OSError, pd.errors.ParserError) as exc:
        logger.warning("Could not read %s: %s", relations_path, exc)
        return None

    for column in ("source", "target", "relation", "evidence"):
        if column not in frame.columns:
            frame[column] = ""
    frame = frame.fillna("")

    relations: list[Relation] = []
    for row in frame.to_dict("records"):
        source = _normalise_key(row.get("source"))
        target = _normalise_key(row.get("target"))
        if not source or not target:
            continue
        relations.append(
            Relation(
                source=node_key(PLATFORM_SOURCE_ID, source),
                target=node_key(PLATFORM_SOURCE_ID, target),
                relation=_normalise_key(row.get("relation")),
                evidence=str(row.get("evidence") or "").strip(),
                source_type=str(row.get("source_type") or "未知类型").strip() or "未知类型",
                target_type=str(row.get("target_type") or "未知类型").strip() or "未知类型",
                source_file=str(row.get("source_file") or "").strip(),
                chunk_id=_optional(row.get("chunk_id")),
            )
        )

    if not relations:
        return None
    return _finish(PLATFORM_SOURCE_ID, relations)


def load_inherited_source(path: Path | None) -> GraphSource | None:
    """The inherited Microsoft GraphRAG export, if it is present."""
    if path is None or not path.exists():
        return None

    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError, ImportError) as exc:
        logger.warning("Could not read inherited GraphRAG parquet %s: %s", path, exc)
        return None

    for column in ("source", "target", "description"):
        if column not in frame.columns:
            logger.warning("Inherited parquet %s is missing column %s", path, column)
            return None

    relations: list[Relation] = []
    for row in frame.to_dict("records"):
        source = _normalise_key(row.get("source"))
        target = _normalise_key(row.get("target"))
        if not source or not target:
            continue
        relations.append(
            Relation(
                source=node_key(INHERITED_SOURCE_ID, source),
                target=node_key(INHERITED_SOURCE_ID, target),
                # No relation-type column exists; the description is the relation.
                relation="",
                evidence=str(row.get("description") or "").strip(),
                source_type="未知类型",
                target_type="未知类型",
                source_file=path.name,
                chunk_id=None,
                weight=_as_float(row.get("weight"), 1.0),
                rank=_as_int(row.get("rank"), 0),
                source_degree=_as_int(row.get("source_degree"), 0),
                target_degree=_as_int(row.get("target_degree"), 0),
            )
        )

    if not relations:
        return None

    source_obj = _finish(INHERITED_SOURCE_ID, relations)
    source_obj.provenance = f"inherited:{path}"
    source_obj.label = "继承图谱（合作方 GraphRAG）"
    source_obj.label_key = "kg.source.inherited"
    return source_obj


def _finish(source_id: str, relations: list[Relation]) -> GraphSource:
    graph, undirected, node_types = build_graph(relations)
    positions = {relation.key: index for index, relation in enumerate(relations)}
    return GraphSource(
        source_id=source_id,
        label=source_id,
        provenance=source_id,
        relations=relations,
        graph=graph,
        undirected=undirected,
        node_types=node_types,
        relation_positions=positions,
    )


def _namespace_occurrences(
    occurrences: dict[tuple[str, str, str], list[dict[str, Any]]],
    source_id: str,
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    """Occurrence files store plain entity names; the graph stores namespaced
    keys. Re-key them so the two can be looked up the same way."""
    namespaced: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for (source, relation, target), rows in occurrences.items():
        key = (
            node_key(source_id, source),
            relation,
            node_key(source_id, target),
        )
        namespaced[key] = rows
    return namespaced


def _optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def find_inherited_path(project_root: Path) -> Path | None:
    for relative in INHERITED_RELATIVE_PATHS:
        candidate = project_root / relative
        if candidate.exists():
            return candidate
    return None


def resolve_sources(
    *,
    config: GraphRagConfig,
    runtime_dir: Path | None,
    baseline_dir: Path | None,
    project_root: Path | None = None,
    inherited_path: Path | None = None,
) -> list[GraphSource]:
    """Load every configured source that actually has data on disk."""
    requested = set(config.sources)
    sources: list[GraphSource] = []

    if PLATFORM_SOURCE_ID in requested:
        platform = load_platform_source(runtime_dir, baseline_dir)
        if platform is not None:
            sources.append(platform)
        else:
            logger.info("GraphRAG: no platform graph found; skipping that source.")

    if INHERITED_SOURCE_ID in requested:
        path = inherited_path
        if path is None and project_root is not None:
            path = find_inherited_path(project_root)
        inherited = load_inherited_source(path)
        if inherited is not None:
            sources.append(inherited)
        else:
            logger.info("GraphRAG: no inherited GraphRAG parquet found; skipping that source.")

    return sources
