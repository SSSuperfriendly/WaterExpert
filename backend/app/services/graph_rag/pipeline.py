"""The ``search()`` entry point: question in, grounded and cited answer out.

Everything else in the package is a stage; this module is the assembly, plus the
two things that only make sense at the top level:

**Index memoisation.** The inherited source's index costs seconds to build, so
it is built once per process and keyed on the *filesystem state* it was built
from — every candidate path's ``(mtime_ns, size)``. A rebuild of the platform
graph therefore invalidates it automatically, and a stale index can never be
served after the graph changed on disk. The whole load runs under one
``threading.Lock``, because two concurrent requests must not build it twice.

**Byte-compatible legacy fields.** ``question``/``answer``/``matched_relations``/
``source`` keep their names, types and meanings. Everything GraphRAG adds is
additive, so existing consumers — the ``KgQaResult`` contract, the download
routes, the current UI — keep working against a response that now carries much
more.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from backend.app.services.graph_rag.answering import answer, build_materials
from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.entity_link import EntityLinker
from backend.app.services.graph_rag.global_search import (
    COMMUNITIES_FILE,
    SUMMARIES_FILE,
    attach_source_communities,
    search_communities,
)
from backend.app.services.graph_rag.index import (
    GRAPH_RAG_VERSION,
    IndexBundle,
    Relation,
    content_hash,
    load_index,
)
from backend.app.services.graph_rag.local_search import (
    PathCandidate,
    attach_chunks,
    dedupe,
    detect_intent,
    fuse,
    path_relations,
    rank_by_lexical,
    search_source,
    seed_edges,
    select_paths,
)
from backend.app.services.graph_rag.router import (
    GLOBAL,
    HYBRID,
    LOCAL,
    NONE,
    classify_with_llm,
    route,
)
from backend.app.services.graph_rag.sources import (
    INHERITED_SOURCE_ID,
    PLATFORM_RELATIONS_FILE,
    PLATFORM_SOURCE_ID,
    resolve_sources,
)

logger = logging.getLogger(__name__)

#: Files whose contents change what the index contains. Any change to any of
#: them invalidates the memoised bundle.
_PLATFORM_FILES = (
    PLATFORM_RELATIONS_FILE,
    "chunks.jsonl",
    "occurrences.jsonl",
    COMMUNITIES_FILE,
    SUMMARIES_FILE,
)

_LOAD_LOCK = threading.Lock()
_CACHE: dict[Any, tuple[IndexBundle, EntityLinker, dict[str, Path]]] = {}


def _platform_dir(
    runtime_dir: Path | None,
    baseline_dir: Path | None,
) -> Path | None:
    """Which directory the platform source will actually be read from.

    Mirrors :func:`sources.load_platform_source`'s runtime-then-baseline choice
    so that ``communities.json`` is looked for next to the ``relations.csv``
    that was used.
    """
    for directory in (runtime_dir, baseline_dir):
        if directory is not None and (directory / PLATFORM_RELATIONS_FILE).exists():
            return directory
    return None


def _stat_signature(path: Path) -> tuple[str, int, int] | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return (str(path), info.st_mtime_ns, info.st_size)


def fingerprint(
    config: GraphRagConfig,
    runtime_dir: Path | None,
    baseline_dir: Path | None,
    inherited_path: Path | None,
) -> tuple[Any, ...]:
    """The identity of an index: what it was built from, and how.

    The config terms are only the ones that change the *built* artifact. Ranking
    weights and thresholds are applied per query and so are not part of it.
    """
    candidates: list[Path] = []
    for directory in (runtime_dir, baseline_dir):
        if directory is not None:
            candidates.extend(directory / name for name in _PLATFORM_FILES)
    if inherited_path is not None:
        candidates.append(inherited_path)
        candidates.append(inherited_path.parent / COMMUNITIES_FILE)

    return (
        tuple(config.sources),
        config.tfidf_ngram_max,
        config.evidence_aliases,
        config.communities_enabled,
        tuple(_stat_signature(path) for path in candidates),
    )


def load_bundle(
    config: GraphRagConfig,
    *,
    runtime_dir: Path | None = None,
    baseline_dir: Path | None = None,
    project_root: Path | None = None,
    inherited_path: Path | None = None,
) -> tuple[IndexBundle, EntityLinker, dict[str, Path]]:
    """The memoised ``(bundle, linker, source directories)`` triple."""
    key = fingerprint(config, runtime_dir, baseline_dir, inherited_path)
    with _LOAD_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            return cached

        bundle = _build_bundle(
            config,
            runtime_dir=runtime_dir,
            baseline_dir=baseline_dir,
            project_root=project_root,
            inherited_path=inherited_path,
        )
        linker = EntityLinker(bundle, config)
        directories = _source_directories(bundle, runtime_dir, baseline_dir, inherited_path)

        # One entry only: two live bundles would mean two ~15 MB lexical
        # matrices on a box with 3.4 GiB, for a swap nobody asked for.
        _CACHE.clear()
        _CACHE[key] = (bundle, linker, directories)
        return bundle, linker, directories


def _build_bundle(
    config: GraphRagConfig,
    *,
    runtime_dir: Path | None,
    baseline_dir: Path | None,
    project_root: Path | None,
    inherited_path: Path | None,
) -> IndexBundle:
    sources = resolve_sources(
        config=config,
        runtime_dir=runtime_dir,
        baseline_dir=baseline_dir,
        project_root=project_root,
        inherited_path=inherited_path,
    )

    decisions: dict[str, Path] = {}
    platform_dir = _platform_dir(runtime_dir, baseline_dir)
    if platform_dir is not None:
        decisions[PLATFORM_SOURCE_ID] = platform_dir
    if inherited_path is not None:
        decisions[INHERITED_SOURCE_ID] = inherited_path.parent

    # Communities must exist *before* the lexical index is built: a community's
    # summary is one of its documents.
    for source in sources:
        attach_source_communities(
            source,
            config,
            directory=decisions.get(source.source_id),
            content_hash_value=content_hash(
                (decisions.get(source.source_id) or Path()) / PLATFORM_RELATIONS_FILE,
                (decisions.get(source.source_id) or Path()) / "occurrences.jsonl",
            ),
        )

    return load_index(
        sources,
        config=config,
        content_hash_value=_bundle_content_hash(sources, decisions),
    )


def _bundle_content_hash(sources: list[Any], directories: dict[str, Path]) -> str:
    for source in sources:
        if source.source_id == PLATFORM_SOURCE_ID:
            directory = directories.get(PLATFORM_SOURCE_ID)
            if directory is not None:
                return content_hash(
                    directory / PLATFORM_RELATIONS_FILE,
                    directory / "occurrences.jsonl",
                )
    return ""


def _source_directories(
    bundle: IndexBundle,
    runtime_dir: Path | None,
    baseline_dir: Path | None,
    inherited_path: Path | None,
) -> dict[str, Path]:
    directories: dict[str, Path] = {}
    if PLATFORM_SOURCE_ID in bundle.sources:
        platform_dir = _platform_dir(runtime_dir, baseline_dir)
        if platform_dir is not None:
            directories[PLATFORM_SOURCE_ID] = platform_dir
    if INHERITED_SOURCE_ID in bundle.sources and inherited_path is not None:
        directories[INHERITED_SOURCE_ID] = inherited_path.parent
    return directories


def platform_provenance(bundle: IndexBundle) -> str:
    """``runtime`` / ``baseline`` / ``none`` — the legacy ``source`` field."""
    source = bundle.sources.get(PLATFORM_SOURCE_ID)
    if source is None:
        return "none"
    return source.provenance.partition(":")[0] or "none"


def merge_relations(
    path_edges: list[Relation],
    backfill: list[Relation],
    config: GraphRagConfig,
) -> list[Relation]:
    """Union of the ranked paths' edges and the backfill, capped.

    Path edges come first because the path list is the *ranking*: an edge that
    earned a place in a top-scoring path has been judged relevant by the fusion
    of structure, lexical overlap, seed coverage and intent. The backfill —
    seed-adjacent edges, then community edges — exists so that a direct claim
    the path ranking happened to skip is still available to the prompt rather
    than being lost to an arbitrary cut.

    The backfill's remaining slots are then shared **round-robin between
    sources**, not filled in list order. Concatenating instead lets the larger
    graph decide the prompt by sheer size: the inherited source has 18k edges to
    the platform's 87, so any question that links into both gets a handful of
    platform relations and then nine inherited ones — including, on a
    platform-only question, nine edges whose only qualification is that they
    touch a node the synonym table happened to link. The two sources answer
    different questions here, and neither should be able to crowd the other out
    of a budget of twelve. A source that runs out of candidates simply yields
    its turn back, so a single-source question still fills every slot.
    """
    out: list[Relation] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in path_edges:
        if edge.key in seen:
            continue
        seen.add(edge.key)
        out.append(edge)
        if len(out) >= config.max_relations:
            return out

    by_source: dict[str, list[Relation]] = {}
    for edge in backfill:
        if edge.key in seen:
            continue
        by_source.setdefault(edge.source.partition("::")[0], []).append(edge)

    order = sorted(by_source)
    while order and len(out) < config.max_relations:
        for source_id in list(order):
            group = by_source[source_id]
            if not group:
                order.remove(source_id)
                continue
            edge = group.pop(0)
            if edge.key in seen:
                continue
            seen.add(edge.key)
            out.append(edge)
            if len(out) >= config.max_relations:
                break
        if all(not by_source[source_id] for source_id in order):
            break
    return out


def _community_count(bundle: IndexBundle) -> int:
    return sum(len(source.communities or []) for source in bundle.sources.values())


def _not_found_answer(bundle: IndexBundle, mode: str) -> str:
    """The honest refusal, worded for *why* nothing was found.

    Refusing is a real answer here, not an error path: the whole design is
    entity-anchored, so a question the linker cannot attach to any entity in the
    graph is a question this system should decline rather than answer from the
    least-dissimilar community.
    """
    if bundle.is_empty:
        return "当前没有可用的知识图谱：平台图谱与继承图谱都未找到。"
    if mode == NONE:
        return "当前知识图谱中没有足够信息回答该问题：问题未命中图谱中的任何实体。"
    return "当前知识图谱中没有足够信息回答该问题。"


def search(
    question: str,
    *,
    config: GraphRagConfig | None = None,
    runtime_dir: Path | None = None,
    baseline_dir: Path | None = None,
    project_root: Path | None = None,
    inherited_path: Path | None = None,
    mode: str | None = None,
    use_llm: bool = True,
    top_k: int | None = None,
    max_relations: int | None = None,
) -> dict[str, Any]:
    """Answer ``question`` from the knowledge graphs, with citations.

    ``mode`` forces ``local``/``global``/``hybrid``/``none`` and skips routing;
    ``use_llm=False`` guarantees the deterministic renderer runs, which is what
    the agent-injection path and the evaluation harness both need.
    """
    started = time.perf_counter()
    question = (question or "").strip()
    if not question:
        raise ValueError("请输入问题。")

    config = config or GraphRagConfig.from_env()
    overrides: dict[str, Any] = {}
    if top_k is not None:
        overrides["top_k"] = int(top_k)
    if max_relations is not None:
        overrides["max_relations"] = int(max_relations)
    if overrides:
        config = config.with_overrides(**overrides)

    bundle, linker, _directories = load_bundle(
        config,
        runtime_dir=runtime_dir,
        baseline_dir=baseline_dir,
        project_root=project_root,
        inherited_path=inherited_path,
    )

    notes: list[str] = list(bundle.notes)
    seeds = linker.link(question)
    community_count = _community_count(bundle)

    if mode is not None:
        chosen = mode
        scores = {"local": 0.0, "global": 0.0}
        notes.append(f"检索模式由调用方指定为 {mode}。")
    else:
        chosen, scores, route_notes = _resolve_mode(question, seeds, bundle, config, community_count)
        notes.extend(route_notes)

    paths: list[PathCandidate] = []
    path_edges: list[Relation] = []
    backfill: list[Relation] = []
    communities: list[dict[str, Any]] = []
    global_usable = config.communities_enabled and community_count >= 2

    if chosen in (LOCAL, HYBRID) and seeds:
        paths, path_edges, backfill = _local_stage(bundle, seeds, question, config)
        if not path_edges and not backfill and chosen == LOCAL and global_usable:
            # Nothing local matched, but a survey might. The router cannot see
            # this — it only has the question and the seeds — so the fallback
            # belongs here, where the empty retrieval is a fact.
            notes.append("本地检索无结果，追加全局检索。")
            chosen = HYBRID

    if chosen in (GLOBAL, HYBRID) and global_usable:
        communities = search_communities(bundle, question, seeds, config)
        backfill = [edge for community in communities for edge in community["relations"]] + backfill
    elif chosen == GLOBAL and not global_usable:
        chosen = LOCAL
        notes.append("社区能力不可用，全局检索降级为本地检索。")

    relations = merge_relations(path_edges, backfill, config)
    chunks = attach_chunks(bundle, relations, config)

    if not relations and not communities:
        stats: dict[str, Any] = {
            "citation_validity": 1.0,
            "groundedness": 1.0,
            "hallucinated_markers": [],
            "used_markers": [],
            "llm_called": False,
            "insufficient": True,
        }
        text = _not_found_answer(bundle, chosen)
        citations: list[dict[str, Any]] = []
    else:
        materials, citations, _markers = build_materials(
            bundle, paths, relations, chunks, communities
        )
        text, stats = answer(
            question,
            materials,
            citations,
            paths=paths,
            relations=relations,
            chunks=chunks,
            communities=communities,
            llm_configured=use_llm and _llm_configured(),
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return _response(
        question=question,
        text=text,
        stats=stats,
        citations=citations,
        bundle=bundle,
        mode=chosen,
        scores=scores,
        paths=paths,
        relations=relations,
        chunks=chunks,
        communities=communities,
        seeds=seeds,
        notes=notes,
        elapsed_ms=elapsed_ms,
    )


def _resolve_mode(
    question: str,
    seeds: list[Any],
    bundle: IndexBundle,
    config: GraphRagConfig,
    community_count: int,
) -> tuple[str, dict[str, float], list[str]]:
    if config.llm_router:
        llm_mode = classify_with_llm(question)
        if llm_mode is not None:
            if llm_mode == NONE:
                return NONE, {"local": 0.0, "global": 0.0}, ["路由器（LLM）判定与知识图谱无关。"]
            if llm_mode == GLOBAL and not (
                config.communities_enabled and community_count >= 2
            ):
                return LOCAL, {"local": 0.0, "global": 0.0}, [
                    "路由器（LLM）选择 global，但社区能力不可用，回退到 local。"
                ]
            return llm_mode, {"local": 0.0, "global": 0.0}, [f"路由器（LLM）判定为 {llm_mode}。"]
    return route(question, seeds, bundle, config, community_count=community_count)


def _local_stage(
    bundle: IndexBundle,
    seeds: list[Any],
    question: str,
    config: GraphRagConfig,
) -> tuple[list[PathCandidate], list[Relation], list[Relation]]:
    """Run local retrieval and return ``(paths, path edges, seed-adjacent edges)``."""
    intent_type = detect_intent(question)
    candidates: list[PathCandidate] = []
    adjacent: list[Relation] = []

    for source in bundle.sources.values():
        source_seeds = [seed for seed in seeds if seed.source_id == source.source_id]
        if not source_seeds:
            continue
        candidates.extend(
            search_source(bundle, source, source_seeds, question, config, intent_type)
        )
        adjacent.extend(seed_edges(source, source_seeds))

    fuse(candidates, config)
    paths = select_paths(dedupe(candidates, config), config)
    return paths, path_relations(paths, config), rank_by_lexical(bundle, adjacent, question)


def _llm_configured() -> bool:
    from backend.app.services.kg_llm import is_llm_configured

    return is_llm_configured()


def _response(
    *,
    question: str,
    text: str,
    stats: dict[str, Any],
    citations: list[dict[str, Any]],
    bundle: IndexBundle,
    mode: str,
    scores: dict[str, float],
    paths: list[PathCandidate],
    relations: list[Relation],
    chunks: list[dict[str, Any]],
    communities: list[dict[str, Any]],
    seeds: list[Any],
    notes: list[str],
    elapsed_ms: int,
) -> dict[str, Any]:
    """Assemble the wire response.

    The first four keys are the legacy contract, unchanged. ``_score`` on a
    matched relation is now the relation's own retrieval score rather than the
    old integer heuristic — the field is still present and still descending, and
    nothing but the ranking ever read it.
    """
    ranked = {relation.key: index for index, relation in enumerate(relations)}
    total = max(len(relations), 1)

    matched_relations = []
    for relation in relations:
        position = ranked[relation.key]
        matched_relations.append(
            {**relation.as_dict(), "_score": round((total - position) / total, 4)}
        )

    sources = bundle.sources
    platform_source = sources.get(PLATFORM_SOURCE_ID)

    # "Degraded" means the pipeline ran in a reduced mode, not that the answer
    # was a refusal. A ``none`` result with no relations is the system working as
    # designed, so it must not be flagged — otherwise every out-of-scope question
    # would look like a malfunction in the dashboard.
    degraded = bool(
        stats.get("llm_error")
        or stats.get("llm_unstructured")
        or platform_source is None
        or (mode != NONE and not relations)
    )

    return {
        # ---- legacy contract, byte-compatible ----------------------------
        "question": question,
        "answer": text,
        "matched_relations": matched_relations,
        "source": platform_provenance(bundle),
        # ---- GraphRAG additions -------------------------------------------
        "mode": mode,
        "graph_rag_version": GRAPH_RAG_VERSION,
        "capabilities": bundle.capabilities(),
        "sources": bundle.describe_sources(),
        "paths": [
            path.as_dict(sources[path.source_id], path_id=f"p{index}")
            for index, path in enumerate(paths, start=1)
            if path.source_id in sources
        ],
        "chunks": chunks,
        "communities": [
            {
                "community_id": community.get("community_id", ""),
                "source_id": community.get("source_id", ""),
                "size": community.get("size", 0),
                "summary": community.get("summary", ""),
                "summary_mode": community.get("summary_mode", "extractive"),
                "top_nodes": list(community.get("nodes") or [])[:12],
                "score": community.get("score", 0.0),
            }
            for community in communities
        ],
        "citations": citations,
        "seed_entities": [seed.as_dict() for seed in seeds],
        "stats": {
            "relation_count": bundle.relation_count,
            "path_count": len(paths),
            "seed_count": len(seeds),
            "community_count": _community_count(bundle),
            "elapsed_ms": elapsed_ms,
            "llm_called": bool(stats.get("llm_called")),
            "degraded": degraded,
            "citation_validity": stats.get("citation_validity", 0.0),
            "groundedness": stats.get("groundedness", 0.0),
            "hallucinated_markers": stats.get("hallucinated_markers", []),
            "router_scores": scores,
            "notes": notes,
        },
    }


def deterministic_summary(
    result: dict[str, Any], max_chars: int = 1500, include_relations: bool = True
) -> str:
    """A prose digest of a search result, built without calling a model.

    This is what the agent-injection path sends. The agent request is already
    the expensive one; fanning a second paid call out of it would double the
    cost of every agent question for a summary the graph can state itself.

    ``include_relations=False`` omits the edge listing for callers that also
    send the edges as structured data. The agent context does exactly that, and
    a payload that states the same eight edges twice spends prompt budget
    saying nothing new — once in prose the model must re-read, once in the
    list it is actually meant to cite.
    """
    lines: list[str] = []
    stats = result.get("stats") or {}
    mode = result.get("mode")

    if result.get("communities"):
        for community in result["communities"]:
            summary = str(community.get("summary") or "").strip()
            if summary:
                lines.append(summary)

    relations = result.get("matched_relations") or []
    if relations and include_relations:
        lines.append("相关图谱关系：")
        for relation in relations[:10]:
            source = relation.get("source", "")
            target = relation.get("target", "")
            label = relation.get("relation") or relation.get("evidence") or ""
            lines.append(f"- {source} --{label}--> {target}")

    for path in (result.get("paths") or [])[:3]:
        nodes = path.get("nodes") or []
        if len(nodes) >= 2:
            lines.append("关联链路：" + " → ".join(str(node) for node in nodes))

    if not lines:
        lines.append(str(result.get("answer") or "").strip())

    if not lines:
        return ""

    header = f"（检索模式：{mode}；命中 {stats.get('seed_count', 0)} 个实体、{stats.get('path_count', 0)} 条路径）"
    return (header + "\n" + "\n".join(lines)).strip()[:max_chars]
