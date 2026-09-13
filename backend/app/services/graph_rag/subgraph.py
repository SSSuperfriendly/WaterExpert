"""The drawable subgraph behind one answer.

The canvas used to be handed the whole platform graph plus a list of ids to
brighten. That only ever works while the ids and the drawn nodes come from the
same graph, and they no longer do: retrieval runs over ``platform`` *and*
``inherited``, while ``graph.json`` holds the 66 platform nodes alone. An answer
grounded in the inherited graph therefore asked the canvas to focus entities it
had never drawn — 18,157 English edges against 66 Chinese nodes, an intersection
that is empty by construction.

So the canvas now asks for what it should *draw*, rather than being told what to
brighten. Identity is the namespaced key (``platform::浊度``) — the exact string
``Relation`` already uses internally, which ``as_dict`` used to strip for the
wire. Request, response and highlight all speak that one vocabulary, so the two
cannot disagree about what a name means.

Referential integrity is not a nicety here, it is the failure mode. vis-network
raises on an edge whose endpoint is not a node in the same ``DataSet``, so this
module never emits an edge without both of its endpoints, and it never reports a
node it did not find. Anything asked for and missing comes back in ``missing``
instead of being silently dropped — an honest gap is debuggable, a silent one is
the bug this file exists to end.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.app.services.graph_rag.index import (
    GraphSource,
    IndexBundle,
    node_key,
    split_node_key,
)

#: A hard ceiling on what is drawn. ``TURBIDITY`` alone has 593 edges in the
#: inherited graph, and one hop from a hub entity would otherwise pull a
#: thousand nodes into a browser layout that is O(n²) to settle.
MAX_SUBGRAPH_EDGES = 300
MAX_SUBGRAPH_NODES = 400

#: How many communities one request may expand. Each contributes at most
#: ``COMMUNITY_NODE_LIMIT`` (60) members, so this bounds the node growth.
MAX_COMMUNITIES = 8


def _as_key(ref: Any) -> tuple[str, str] | None:
    """Read one requested entity into ``(source_id, name)``.

    Accepts ``{"source_id": ..., "name": ...}`` and the already-namespaced
    ``"platform::浊度"``. The second form is what the API returns, so accepting
    it means a caller can round-trip a node id without taking it apart.
    """
    if isinstance(ref, str):
        text = ref.strip()
        if not text:
            return None
        if "::" in text:
            source_id, name = split_node_key(text)
            return (source_id, name) if source_id and name else None
        # A bare name is ambiguous across two graphs. Refusing it is the point:
        # guessing here is what produced the original crash.
        return None
    if isinstance(ref, dict):
        source_id = str(ref.get("source_id") or "").strip()
        name = str(ref.get("name") or "").strip()
        if name and "::" in name and not source_id:
            source_id, name = split_node_key(name)
        if source_id and name:
            return source_id, name
    return None


def _edge_id(relation: Any, multi_key: Any) -> str:
    """A stable, unique id for one edge — unique even between parallel edges.

    ``vis.DataSet`` keys edges by id, so two relations between the same ordered
    pair collapse into one the moment they share an id. The multi-edge key is
    what distinguishes them, and it comes from the graph rather than from a
    counter over this particular response.
    """
    return f"{relation.source}>{relation.target}#{multi_key}"


def _resolve_keys(
    bundle: IndexBundle, refs: Iterable[Any]
) -> tuple[dict[str, list[str]], set[str], list[dict[str, str]]]:
    """Split the requested entities into per-source hits and honest misses."""
    by_source: dict[str, list[str]] = {}
    known: set[str] = set()
    missing: list[dict[str, str]] = []

    for ref in refs:
        parsed = _as_key(ref)
        if parsed is None:
            continue
        source_id, name = parsed
        key = node_key(source_id, name)
        if key in known:
            continue
        known.add(key)
        source = bundle.sources.get(source_id)
        if source is None or key not in source.graph:
            missing.append({"source_id": source_id, "name": name})
            continue
        by_source.setdefault(source_id, []).append(key)

    return by_source, known, missing


def _community_keys(
    bundle: IndexBundle, community_ids: Iterable[Any]
) -> tuple[set[str], list[str]]:
    """Members of the named communities, as namespaced keys.

    A community is addressed by ``community_id`` alone, so every source is
    searched for it. Members come from the persisted ``node_keys`` — the
    namespaced form — because the display names a community also carries are
    ambiguous between the two graphs.
    """
    wanted = [str(value).strip() for value in community_ids if str(value).strip()]
    if not wanted:
        return set(), []

    found: set[str] = set()
    unresolved: list[str] = []
    for community_id in wanted[:MAX_COMMUNITIES]:
        hit = False
        for source in bundle.sources.values():
            for community in source.communities or []:
                if community.get("community_id") != community_id:
                    continue
                hit = True
                for key in community.get("node_keys") or []:
                    if key in source.graph:
                        found.add(key)
        if not hit:
            unresolved.append(community_id)
    return found, unresolved


def _fill(
    bundle: IndexBundle, candidates: set[str], chosen: set[str], cap: int
) -> tuple[set[str], bool]:
    """Add as many ``candidates`` as the node budget allows, best-connected first.

    The budget is spent here, before any edge is chosen, because the two orders
    are not interchangeable. An over-large node set cannot be rescued by trimming
    edges: every remaining edge still has endpoints outside the cap, so the trim
    runs to completion and returns a screenful of unconnected dots. The node
    count is what has to give, and it has to give first.

    Degree ranks the candidates because a hub explains why an entity shows up in
    many relations and a degree-1 leaf explains nothing. Ties break on the key so
    the same request always draws the same graph.

    The second return value says the budget ran out with candidates still
    waiting. Dropping them silently would make "this entity has no neighbours"
    and "this entity's neighbours did not fit" look identical from the outside,
    and only one of those is worth acting on.
    """
    budget = cap - len(chosen)
    pending = [key for key in candidates if key not in chosen]
    if not pending:
        return set(), False
    if budget <= 0:
        return set(), True

    degree: dict[str, int] = {}
    for source in bundle.sources.values():
        graph = source.graph
        for key in pending:
            if key in graph:
                # A node key belongs to exactly one source, so the max over
                # sources is simply that node's degree.
                degree[key] = max(degree.get(key, 0), int(graph.degree(key)))

    ranked = sorted(degree.items(), key=lambda item: (-item[1], item[0]))
    return {key for key, _degree in ranked[:budget]}, len(ranked) > budget


def _one_hop(bundle: IndexBundle, wanted: set[str]) -> set[str]:
    """Every neighbour of ``wanted``, one hop out."""
    neighbours: set[str] = set()
    for source in bundle.sources.values():
        graph = source.graph
        for key in wanted:
            if key not in graph:
                continue
            neighbours.update(graph.successors(key))
            neighbours.update(graph.predecessors(key))
    return neighbours - wanted


def _candidate_edges(
    bundle: IndexBundle, keys: set[str], priority: set[str]
) -> tuple[list[tuple[GraphSource, Any, Any]], list[tuple[GraphSource, Any, Any]]]:
    """Every edge touching ``keys``, ordered, plus the ones reaching outside it.

    The first list holds edges with both endpoints in ``keys``; the second holds
    the rest, and is only drawn when ``include_neighbours`` asked for the
    surroundings.

    ``priority`` is the set of entities the answer itself cited. Those edges sort
    first, which is what keeps a cap honest: when a community expansion brings
    more edges than fit, the ones that get dropped are the ones the user did not
    come here to see. Ordering by id alone would drop citations alphabetically,
    which is to say arbitrarily.
    """
    internal: list[tuple[GraphSource, Any, Any]] = []
    boundary: list[tuple[GraphSource, Any, Any]] = []
    seen: set[str] = set()

    for source in bundle.sources.values():
        graph = source.graph
        for key in sorted(keys):
            if key not in graph:
                continue
            for left, right, multi_key, data in graph.out_edges(key, keys=True, data=True):
                relation = data["relation"]
                edge_id = _edge_id(relation, multi_key)
                if edge_id in seen:
                    continue
                seen.add(edge_id)
                bucket = internal if (left in keys and right in keys) else boundary
                bucket.append((source, relation, (left, right, multi_key)))

    def order(item: tuple[GraphSource, Any, Any]) -> tuple[int, tuple[str, str, Any]]:
        _source, relation, meta = item
        cited = 0 if (relation.source in priority and relation.target in priority) else 1
        return (cited, meta)

    internal.sort(key=order)
    boundary.sort(key=order)
    return internal, boundary


def _node_payload(source: GraphSource, key: str) -> dict[str, Any]:
    _, name = split_node_key(key)
    return {
        "id": key,
        "name": name,
        "source_id": source.source_id,
        "type": source.node_types.get(key, ""),
        "degree": source.degree(key),
    }


def _focus_edge_id(focus: Any, drawn: dict[str, str]) -> str | None:
    """Resolve a requested edge to the id actually drawn for it.

    The caller names an edge by its endpoints, which is all the answer knows.
    Parallel edges share endpoints, so the index disambiguates — and the search
    runs over this response's own drawn set, because an id the canvas was never
    given is not something to hand a highlighter.
    """
    if not isinstance(focus, dict):
        return None
    source_id = str(focus.get("source_id") or "").strip()
    left, right = focus.get("source"), focus.get("target")
    if not (source_id and left and right):
        return None
    index = focus.get("index")
    index = index if isinstance(index, int) and index >= 0 else 0

    wanted = f"{node_key(source_id, str(left))}>{node_key(source_id, str(right))}"
    candidates = sorted(edge_id for edge_id, ends in drawn.items() if ends == wanted)
    if not candidates:
        return None
    return candidates[index] if index < len(candidates) else candidates[0]


def subgraph(
    bundle: IndexBundle,
    *,
    nodes: Iterable[Any] = (),
    community_ids: Iterable[Any] = (),
    include_neighbours: bool = False,
    focus: Any = None,
    max_edges: int = MAX_SUBGRAPH_EDGES,
    max_nodes: int = MAX_SUBGRAPH_NODES,
) -> dict[str, Any]:
    """The drawable nodes and edges around the entities an answer cited.

    Returns a response that is safe to hand straight to ``vis.DataSet``: every
    edge endpoint is present in ``nodes``, every id is unique, and every entity
    that could not be found is reported rather than dropped.
    """
    requested, requested_keys, missing = _resolve_keys(bundle, nodes)
    # The cited entities are the answer's own evidence. They are kept whatever
    # the cap says — dropping one would leave a citation pointing at nothing,
    # which is the failure this endpoint exists to prevent.
    wanted: set[str] = {key for keys in requested.values() for key in keys}

    node_cap = max(1, int(max_nodes))
    community_keys, unresolved_communities = _community_keys(bundle, community_ids)
    picked, truncated = _fill(bundle, community_keys, wanted, node_cap)
    wanted |= picked
    if include_neighbours and wanted:
        picked, dropped = _fill(bundle, _one_hop(bundle, wanted), wanted, node_cap)
        wanted |= picked
        truncated = truncated or dropped

    if not wanted:
        return {
            "nodes": [],
            "edges": [],
            "sources": [],
            "missing": missing,
            "unresolved_communities": unresolved_communities,
            "truncated": False,
            "focus_edge_id": None,
        }

    internal, boundary = _candidate_edges(bundle, wanted, set(requested_keys))
    # Without a neighbour expansion the boundary edges are one hop *outside* the
    # retrieval — real relations, but not ones this answer stands on. Drawing
    # them would put edges on a canvas captioned "what this answer used" that the
    # answer never used, which is the opposite of traceable. They are one click
    # away via ``include_neighbours``.
    candidates = internal + boundary if include_neighbours else internal
    cap = max(1, int(max_edges))
    kept = candidates[:cap]
    truncated = truncated or len(candidates) > len(kept)

    # A node cap must drop *edges*, never just nodes: an edge whose endpoint the
    # canvas does not have is a crash, which is the whole reason this endpoint
    # returns whole subgraphs instead of id lists. With the expansion already
    # bounded this is a net, not the mechanism.
    while kept:
        endpoints = {
            key
            for _source, relation, _meta in kept
            for key in (relation.source, relation.target)
        }
        if len(endpoints | wanted) <= node_cap:
            break
        kept.pop()
        truncated = True

    drawn_edges: list[dict[str, Any]] = []
    drawn_nodes: dict[str, GraphSource] = {}
    for source, relation, (left, right, multi_key) in kept:
        drawn_edges.append(
            {
                "id": _edge_id(relation, multi_key),
                "source_id": source.source_id,
                "source": relation.source,
                "target": relation.target,
                "display_source": relation.display_source,
                "display_target": relation.display_target,
                "relation": relation.relation,
                "evidence": relation.evidence,
                "source_file": relation.source_file,
                "chunk_id": relation.chunk_id,
            }
        )
        drawn_nodes.setdefault(left, source)
        drawn_nodes.setdefault(right, source)

    for source in bundle.sources.values():
        for key in wanted:
            if key in source.graph:
                drawn_nodes.setdefault(key, source)

    order = {source_id: index for index, source_id in enumerate(bundle.order)}
    payload_nodes = [
        _node_payload(source, key)
        for key, source in sorted(
            drawn_nodes.items(), key=lambda item: (order.get(item[1].source_id, 0), item[0])
        )
    ]

    used = {node["source_id"] for node in payload_nodes}
    sources = [
        described
        for described in bundle.describe_sources()
        if described["source_id"] in used
    ]

    drawn_for_focus = {
        edge["id"]: f"{edge['source']}>{edge['target']}" for edge in drawn_edges
    }

    return {
        "nodes": payload_nodes,
        "edges": drawn_edges,
        "sources": sources,
        "missing": missing,
        "unresolved_communities": unresolved_communities,
        "truncated": truncated,
        "focus_edge_id": _focus_edge_id(focus, drawn_for_focus),
    }
