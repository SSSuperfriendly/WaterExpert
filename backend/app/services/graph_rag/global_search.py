"""Communities, their summaries, and global (survey) retrieval.

**Summaries are materialised at build time, never at question time.** That is
the single most important decision in this module. Generating a summary inside
an HTTP handler would mean N paid API calls per question against a metered
endpoint, with a multi-second tail latency on a 2 vCPU box. Instead the build
runner writes ``communities.json`` (pure structure, free) and — when an LLM is
configured — ``summaries.json``, capped at
:attr:`GraphRagConfig.community_max_llm_calls` calls *per rebuild*.

An extractive summary is always available, so the "cached summary" concept
always resolves: with no LLM, with a stale cache, with a corrupt cache, the
question path still returns a real summary and spends nothing.

Global retrieval therefore adds **zero** LLM calls to a question. The evaluation
asserts that mechanically.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx

from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.entity_link import SeedLink
from backend.app.services.graph_rag.index import (
    GraphSource,
    IndexBundle,
    Relation,
    community_doc_id,
    relation_doc_id,
)
from backend.app.services.graph_rag.lexicon import is_junk_entity
from backend.app.time_utils import utc_now

logger = logging.getLogger(__name__)

SUMMARIES_FILE = "summaries.json"
COMMUNITIES_FILE = "communities.json"
SUMMARY_INDEX_VERSION = 1
COMMUNITIES_INDEX_VERSION = 1

#: Coverage bonus for a community whose own nodes the question named.
COVERAGE_BONUS = 0.5

#: Naming this many members already means "this community is the topic"; beyond
#: it the bonus saturates. Deliberately a small absolute count rather than the
#: *fraction* of seeds named: a fraction makes a one-seed question that names
#: that one member score the maximum bonus, which is precisely the shape of a
#: question the graph knows nothing about — it linked one node by accident and
#: would then be handed a whole community as if it were on-topic.
COVERAGE_FULL = 3.0




def detect_communities(
    source: GraphSource,
    config: GraphRagConfig,
) -> list[dict[str, Any]]:
    """Partition one source's undirected projection into communities.

    Community ids are ``{source}:c0001``, numbered after sorting by descending
    size and then by the alphabetically-first member. That makes an id stable
    across rebuilds of an unchanged graph, which is what lets a cached summary
    still match.
    """
    graph = source.undirected
    if graph.number_of_nodes() == 0:
        return []

    try:
        # Louvain, not greedy modularity, and not as a fallback — as the choice.
        # Measured on the 10,567-node / 18,157-edge inherited graph: Louvain
        # 0.21 s to modularity 0.745, greedy 11.0 s to modularity 0.691. Greedy
        # was the plan's default and Louvain its "if it proves slow" fallback;
        # the measurement says the fallback is the better algorithm on both
        # axes, so the wait-for-it-to-be-slow branch is gone.
        #
        # ``weight="count"`` uses the parallel-edge multiplicity the undirected
        # projection carries, so two entities joined by 40 extracted claims are
        # genuinely closer than two joined by one.
        partitions = nx.community.louvain_communities(
            graph,
            weight="count",
            seed=config.community_seed,
        )
    except Exception as exc:  # noqa: BLE001 — communities are an enhancement, not a dependency
        logger.warning("Community detection failed for %s: %s", source.source_id, exc)
        return []

    ordered = sorted(
        (set(members) for members in partitions),
        key=lambda members: (-len(members), min(members)),
    )

    communities: list[dict[str, Any]] = []
    for index, members in enumerate(ordered, start=1):
        relations = _internal_relations(source, members, config)
        if not relations:
            continue
        degree_sorted = sorted(members, key=lambda node: (-source.degree(node), node))
        communities.append(
            {
                "community_id": f"{source.source_id}:c{index:04d}",
                "source_id": source.source_id,
                "size": len(members),
                "nodes": [source.display_name(node) for node in degree_sorted],
                "node_keys": degree_sorted,
                "top_relations": [relation.as_dict() for relation in relations],
            }
        )
    return communities


def _internal_relations(
    source: GraphSource,
    members: set[str],
    config: GraphRagConfig,
) -> list[Relation]:
    """The strongest edges wholly inside a community, junk endpoints excluded."""
    out: list[Relation] = []
    for node in members:
        for neighbour, edges in _neighbours(source, node).items():
            if neighbour not in members:
                continue
            for edge in edges:
                if is_junk_entity(edge.display_source) or is_junk_entity(edge.display_target):
                    continue
                out.append(edge)
    out.sort(key=lambda relation: (-source.degree(relation.source) - source.degree(relation.target), relation.key))
    return out[: config.community_max_edges]


def _neighbours(source: GraphSource, node: str) -> dict[str, list[Relation]]:
    neighbours: dict[str, list[Relation]] = {}
    if node not in source.graph:
        return neighbours
    for _start, end, data in source.graph.out_edges(node, data=True):
        neighbours.setdefault(end, []).append(data["relation"])
    for start, _end, data in source.graph.in_edges(node, data=True):
        neighbours.setdefault(start, []).append(data["relation"])
    return neighbours


def extractive_summary(community: dict[str, Any], config: GraphRagConfig) -> str:
    """A summary built only from what the graph already says. Costs nothing.

    This is the floor the system never falls below: every community has one,
    whether or not an LLM was ever configured.
    """
    names = [name for name in community.get("nodes", []) if not is_junk_entity(name)][:12]
    if not names:
        return f"该社区包含 {community.get('size', 0)} 个实体。"

    lines = [f"该社区包含 {community.get('size', 0)} 个实体，核心实体为：" + "、".join(names) + "。"]
    for relation in community.get("top_relations", [])[:6]:
        source = str(relation.get("source") or "")
        target = str(relation.get("target") or "")
        relation_label = str(relation.get("relation") or "")
        evidence = str(relation.get("evidence") or "")
        if relation_label:
            lines.append(f"{source} --{relation_label}--> {target}：{evidence}")
        else:
            lines.append(f"{source} --({evidence})--> {target}")
    return "\n".join(lines)[: config.summary_max_chars]


def summarise_communities(
    communities: list[dict[str, Any]],
    config: GraphRagConfig,
    *,
    call_llm: Any = None,
    on_progress: Any = None,
) -> list[dict[str, Any]]:
    """Attach a summary to every community, LLM-written for the largest few.

    ``call_llm`` being ``None`` (or raising) is a normal, supported outcome:
    every community then gets its extractive summary and the run continues.
    """
    ordered = sorted(communities, key=lambda item: -item.get("size", 0))
    budget = config.community_max_llm_calls if (config.summaries_enabled and call_llm) else 0
    # What the progress callback counts towards: the budget caps the *work*, but
    # a graph with four communities never reaches twelve, and a counter that
    # stops at 4/12 reads as a stalled job.
    planned = min(budget, len(ordered))

    out: list[dict[str, Any]] = []
    for index, community in enumerate(ordered):
        summary = extractive_summary(community, config)
        mode = "extractive"
        model = ""

        if index < budget:
            if on_progress is not None:
                on_progress(index + 1, planned, community.get("community_id", ""))
            try:
                generated = call_llm(_summary_prompt(community))
            except Exception as exc:  # noqa: BLE001 — a failed summary is a cheaper summary, not a failed build
                logger.warning("Community summary failed for %s: %s", community.get("community_id"), exc)
                generated = ""
            if generated and generated.strip():
                summary = generated.strip()[: config.summary_max_chars]
                mode = "llm"
                model = _model_name()

        out.append(
            {
                **community,
                "summary": summary,
                "summary_mode": mode,
                "model": model,
            }
        )
    return out


def _model_name() -> str:
    from backend.app.services.kg_llm import get_llm_config

    return get_llm_config()["model"]


_SUMMARY_PROMPT = """下面是一个知识图谱社区的实体与内部关系。请用 3-5 句中文概括这个社区在讲什么。

要求：
1. 只能使用下面列出的关系，不要补充外部知识；
2. 概括主题与主要结论，不要逐条罗列三元组；
3. 直接输出概括文字，不要输出 JSON 或标题。

社区实体：{nodes}

社区内部关系：
{relations}"""


def _summary_prompt(community: dict[str, Any]) -> str:
    nodes = "、".join(community.get("nodes", [])[:25])
    lines = []
    for relation in community.get("top_relations", [])[:25]:
        source = str(relation.get("source") or "")
        target = str(relation.get("target") or "")
        relation_label = str(relation.get("relation") or "")
        evidence = str(relation.get("evidence") or "")
        if relation_label:
            lines.append(f"{source} --{relation_label}--> {target}（{evidence}）")
        else:
            lines.append(f"{source} --({evidence})--> {target}")
    return _SUMMARY_PROMPT.format(nodes=nodes, relations="\n".join(lines))


def write_summaries(path: Path, communities: list[dict[str, Any]], content_hash: str) -> None:
    """Persist the cache. A consumer that cannot use it simply recomputes."""
    payload = {
        "index_version": SUMMARY_INDEX_VERSION,
        "content_hash": content_hash,
        "community_count": len(communities),
        "model": _model_name() if any(c.get("summary_mode") == "llm" for c in communities) else "",
        "generated_at": utc_now(),
        "summaries": [
            {
                "community_id": community.get("community_id", ""),
                "summary": community.get("summary", ""),
                "mode": community.get("summary_mode", "extractive"),
                "model": community.get("model", ""),
            }
            for community in communities
        ],
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_summaries(path: Path, content_hash: str) -> dict[str, dict[str, Any]]:
    """Read the cache, but only when it belongs to the current graph.

    Both the content hash and the community count must match. A mismatch is a
    normal event (the graph was rebuilt) and yields an empty map, not an error.
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if payload.get("content_hash") != content_hash:
        logger.info("Community summary cache is stale (graph changed); recomputing.")
        return {}
    entries = payload.get("summaries")
    if not isinstance(entries, list):
        return {}
    return {
        str(entry.get("community_id")): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("community_id")
    }


def apply_summaries(
    communities: list[dict[str, Any]],
    config: GraphRagConfig,
    cached: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Overlay whichever summaries came from the build-time cache.

    Anything not in the cache — a graph rebuilt since, or a community the cache
    never covered — falls back to the extractive summary, which is always
    computable at question time for free.
    """
    out: list[dict[str, Any]] = []
    for community in communities:
        entry = cached.get(community.get("community_id", ""))
        summary = (entry or {}).get("summary") or extractive_summary(community, config)
        out.append(
            {
                **community,
                "summary": summary,
                "summary_mode": (entry or {}).get("mode", "extractive"),
            }
        )
    return out


def attach_source_communities(
    source: GraphSource,
    config: GraphRagConfig,
    *,
    directory: Path | None = None,
    content_hash_value: str = "",
) -> list[dict[str, Any]]:
    """Give one source its communities, preferring a materialised cache.

    Three outcomes, all of them normal:

    * ``communities.json`` present and usable → load it and overlay whatever
      ``summaries.json`` still matches. No computation at all.
    * no cache (the inherited parquet never has one) → detect and summarise
      extractively, which is free. This is the seconds-long step, and it is why
      the index is memoised and warmed at startup.
    * ``communities_enabled`` off → an empty list, and the router forces local.

    Note what is *absent*: no LLM call, ever. A summary written by the model is
    materialised by the build runner; a question never generates one.
    """
    if not config.communities_enabled:
        source.communities = []
        return []

    loaded: list[dict[str, Any]] | None = None
    cached: dict[str, dict[str, Any]] = {}
    if directory is not None:
        loaded = load_communities(directory / COMMUNITIES_FILE).get(source.source_id)
        if loaded:
            cached = read_summaries(directory / SUMMARIES_FILE, content_hash_value)

    if loaded:
        source.communities = apply_summaries(loaded, config, cached)
    else:
        source.communities = summarise_communities(
            detect_communities(source, config), config
        )
    return source.communities


def search_communities(
    bundle: IndexBundle,
    query: str,
    seeds: list[SeedLink],
    config: GraphRagConfig,
) -> list[dict[str, Any]]:
    """Rank communities, then ground the top ones in concrete edges.

    Two signals: lexical similarity between the question and the community's
    summary-plus-members, and whether the question named any member. The second
    is what makes "太湖的透明度受什么影响" reach the 太湖 community even when the
    summary's wording differs.

    Each selected community then gets a short local search *inside its own node
    set*: its edges are re-ranked against the question. That is what keeps the
    answer from being prose alone — a survey still has to arrive attached to
    specific, citable claims.
    """
    communities = [
        community
        for source in bundle.sources.values()
        for community in (source.communities or [])
    ]
    if not communities or bundle.lexical is None:
        return []

    scores = bundle.lexical.scores(query)
    strength_of = {seed.node_key: seed.score for seed in seeds}

    ranked: list[tuple[float, dict[str, Any]]] = []
    for community in communities:
        position = bundle.lexical.position(community_doc_id(community["community_id"]))
        if position is None:
            continue
        lexical = float(scores[position])
        node_keys = set(community.get("node_keys") or [])
        named = node_keys & set(strength_of)
        if not named:
            # A community is only selectable when the question has a *named
            # foothold* in it. Character n-gram similarity alone is not enough
            # to say a survey is about something: against 400+ Chinese summaries
            # every question shares some single characters with some community,
            # so a lexical-only ranking always returns three confident-looking
            # answers, including for questions the graph knows nothing about.
            continue
        # Weighted by how well the question matched, so a 1.00 exact hit counts
        # for more than a 0.55 related-group hit.
        coverage = min(1.0, len(named) / COVERAGE_FULL) * max(
            strength_of[key] for key in named
        )
        ranked.append((lexical + COVERAGE_BONUS * coverage, community))

    ranked.sort(key=lambda item: (-item[0], item[1].get("community_id", "")))

    # One vectorised pass, shared by every community's re-rank below.
    edge_scores = bundle.lexical.scores(query)

    out: list[dict[str, Any]] = []
    for score, community in ranked[: config.global_top_k]:
        relations = _community_relations(bundle, community, config, edge_scores)
        out.append(
            {
                **community,
                "score": round(score, 4),
                "relations": relations,
            }
        )
    return out


def _community_relations(
    bundle: IndexBundle,
    community: dict[str, Any],
    config: GraphRagConfig,
    edge_scores: Any,
) -> list[Relation]:
    """A community's own edges, re-ranked against the question and capped.

    ``top_relations`` was selected at build time by degree, which says what the
    community is *about* but nothing about what the question asked. The stored
    rows are resolved back to live relations and then ordered by lexical
    relevance, so the edges that reach the prompt are the ones the question is
    actually about — the short in-community search.
    """
    source = bundle.sources.get(community.get("source_id", ""))
    if source is None:
        return []

    out: list[Relation] = []
    seen: set[tuple[str, str, str]] = set()
    for row in community.get("top_relations", []):
        key = (
            f"{community.get('source_id')}::{row.get('source', '')}",
            str(row.get("relation") or ""),
            f"{community.get('source_id')}::{row.get('target', '')}",
        )
        if key in seen:
            continue
        seen.add(key)
        relation = bundle.relation(community.get("source_id", ""), key)
        if relation is not None:
            out.append(relation)

    def relevance(relation: Relation) -> float:
        position = source.relation_positions.get(relation.key)
        index = (
            bundle.lexical.position(relation_doc_id(source.source_id, position))
            if (position is not None and bundle.lexical is not None)
            else None
        )
        return float(edge_scores[index]) if index is not None else 0.0

    out.sort(key=lambda relation: (-relevance(relation), relation.key))
    return out[: config.global_max_edges]


def write_communities(
    path: Path,
    communities: list[dict[str, Any]],
    content_hash_value: str = "",
) -> None:
    """Persist one source's communities, leaving any other source's alone.

    The merge matters because a directory holds one file for every source that
    happens to resolve into it, and a rebuild of one source must not silently
    delete the other's partition — an inherited graph has no rebuild of its own
    to put it back.
    """
    existing = load_communities(path)
    for community in communities:
        existing.pop(str(community.get("source_id") or ""), None)
    source_id = str(communities[0].get("source_id") or "") if communities else ""
    merged = [entry for group in existing.values() for entry in group]
    if source_id:
        merged.extend(community_payload(communities))

    payload = {
        "index_version": COMMUNITIES_INDEX_VERSION,
        "content_hash": content_hash_value,
        "generated_at": utc_now(),
        "communities": merged,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def materialise_source_communities(
    source: GraphSource,
    config: GraphRagConfig,
    directory: Path,
    *,
    content_hash_value: str = "",
    call_llm: Any = None,
    on_progress: Any = None,
) -> list[dict[str, Any]]:
    """Detect one source's communities and write its build-time artifacts.

    This is the *only* place a summary is ever generated, and it runs inside the
    build subprocess, not inside a request. ``call_llm=None`` — no key, or
    summaries switched off — is a supported outcome, not a failure: the
    communities are still written, and the question path falls back to the
    extractive summary it can always compute.

    Deliberately silent about failure. A graph whose communities could not be
    computed is still a perfectly usable graph with local search, so a caller
    that wants to warn can compare the returned length instead of catching.
    """
    if not config.communities_enabled:
        return []

    communities = detect_communities(source, config)
    if not communities:
        return []

    writer = call_llm if (config.summaries_enabled and call_llm is not None) else None
    communities = summarise_communities(
        communities, config, call_llm=writer, on_progress=on_progress
    )

    directory.mkdir(parents=True, exist_ok=True)
    write_communities(directory / COMMUNITIES_FILE, communities, content_hash_value)
    if writer is not None:
        write_summaries(directory / SUMMARIES_FILE, communities, content_hash_value)
    return communities


#: How many members of a community are persisted. Enough for the coverage
#: signal and the prompt, small enough that an 18k-entity graph does not write a
#: multi-megabyte file.
COMMUNITY_NODE_LIMIT = 60


def community_payload(communities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The JSON-safe shape written to ``communities.json``.

    ``node_keys`` is carried alongside the display names on purpose: the
    coverage signal compares a community's members against the *namespaced* seed
    keys, so dropping it would silently disable one of the two ranking signals
    for every community read back from disk.
    """
    return [
        {
            "community_id": community.get("community_id", ""),
            "source_id": community.get("source_id", ""),
            "size": community.get("size", 0),
            "nodes": community.get("nodes", [])[:COMMUNITY_NODE_LIMIT],
            "node_keys": community.get("node_keys", [])[:COMMUNITY_NODE_LIMIT],
            "top_relations": community.get("top_relations", []),
        }
        for community in communities
    ]


def load_communities(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Read ``communities.json`` grouped by source id."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    entries = payload.get("communities") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("community_id"):
            continue
        grouped.setdefault(str(entry.get("source_id") or ""), []).append(entry)
    return grouped
