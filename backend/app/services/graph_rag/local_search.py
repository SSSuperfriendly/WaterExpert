"""Seeds -> scored multi-hop paths.

The deliverable of this module is the *path*, not the triple. ``nx.ego_graph``
is not used because it returns a set of nodes and discards how they connect;
what the answering prompt needs is ``风 →[导致] 沉积物再悬浮 →[影响] 浊度`` — a
causal chain — rather than three unordered edges that happen to share a node.

Expansion is a bounded max-score BFS (a best-first search over paths). Two
properties matter:

* the frontier is ordered by accumulated score, so the first ``max_paths``
  results are the strongest ones rather than whichever the adjacency order
  happened to reach first;
* each path carries its own visited set, so paths are acyclic and every node in
  a path is a real chain of reasoning rather than a walk that doubled back.

Per source, ``hop_depth`` bounds the search. The two sources get different
values on purpose — see :data:`graph_rag.config.DEFAULT_HOP_DEPTH`.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any

from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.entity_link import SeedLink
from backend.app.services.graph_rag.index import (
    Chunk,
    GraphSource,
    IndexBundle,
    Relation,
    relation_doc_id,
)
from backend.app.services.graph_rag.lexicon import INTENT_TYPE_CUES

#: Parallel edges between the same pair are kept in a path, but only this many:
#: a pair joined by 40 edges would otherwise dominate the prompt with one hop.
MAX_PARALLEL_EDGES = 3

#: Path coverage saturates at this many matched seeds — see :func:`search_source`.
COVERAGE_FULL = 3

#: How many of a node's neighbours a traversal may take. Inherited hubs run to
#: hundreds of edges (``TURBIDITY`` has 593), and without a per-node budget one
#: hub consumes the whole record allowance before the next seed is ever
#: expanded. The neighbours kept are the ones the question is lexically about,
#: not the ones that happen to come first in the file — see :func:`expand`.
MAX_NEIGHBOURS_PER_NODE = 24


@dataclass
class PathCandidate:
    """A scored chain of edges, before cross-source fusion."""

    source_id: str
    nodes: list[str]
    edges: list[Relation]
    graph_score: float = 0.0
    lex: float = 0.0
    cov: float = 0.0
    type_hit: float = 0.0
    score: float = 0.0
    score_parts: dict[str, float] = field(default_factory=dict)

    @property
    def hops(self) -> int:
        """Node transitions, not edge count.

        Two nodes joined by two parallel edges are one hop — reporting that as
        ``hops=2`` would make the UI claim a two-step chain for a single step.
        """
        return max(0, len(self.nodes) - 1)

    def signature(self) -> frozenset[tuple[str, str, str]]:
        """Identity of the *chain*: same edges found from different seeds merge."""
        return frozenset(edge.key for edge in self.edges)

    def node_set(self) -> set[str]:
        return set(self.nodes)

    def display_nodes(self, source: GraphSource) -> list[str]:
        return [source.display_name(node) for node in self.nodes]

    def as_dict(self, source: GraphSource, *, path_id: str) -> dict[str, Any]:
        return {
            "path_id": path_id,
            "source_id": self.source_id,
            "nodes": self.display_nodes(source),
            "edges": [edge.as_dict() for edge in self.edges],
            "hops": self.hops,
            "score": round(self.score, 4),
            "score_parts": {key: round(value, 4) for key, value in self.score_parts.items()},
        }


def detect_intent(question: str) -> str | None:
    """The entity type this question is looking for, if it is looking for one.

    Read off the question's wording and resolved against the *seed's* type
    downstream, so a phrasing nobody enumerated still works as long as the
    matching entity carries the right type.
    """
    for cues, entity_type in INTENT_TYPE_CUES:
        if any(cue in question for cue in cues):
            return entity_type
    return None


def incident_edges(source: GraphSource, node: str) -> dict[str, list[Relation]]:
    """Neighbours of ``node`` in either direction, with the edges reaching them.

    The graph is directed — ``风 --导致--> 沉积物再悬浮`` is not symmetric — but a
    traversal is. A question about 浊度 should still reach the edges that point
    *at* it.
    """
    neighbours: dict[str, list[Relation]] = {}
    if node not in source.graph:
        return neighbours
    for _start, end, data in source.graph.out_edges(node, data=True):
        neighbours.setdefault(end, []).append(data["relation"])
    for start, _end, data in source.graph.in_edges(node, data=True):
        neighbours.setdefault(start, []).append(data["relation"])
    return neighbours


def _best_edge_lexical(
    source: GraphSource,
    edges: list[Relation],
    lexical: dict[int, float] | None,
) -> float:
    if lexical is None:
        return 0.0
    return max(
        (lexical.get(source.relation_positions.get(edge.key, -1), 0.0) for edge in edges),
        default=0.0,
    )


def _budget_neighbours(
    neighbours: dict[str, list[Relation]],
    seed_keys: set[str],
    source: GraphSource,
    lexical: dict[int, float] | None,
) -> dict[str, list[Relation]]:
    """Trim a hub's neighbours, never dropping one that is itself a seed.

    An edge whose *both* ends the question named is the strongest candidate the
    graph can offer — it is a claim about two things the user asked about. It
    also scores worst under a purely lexical budget, because a hub's incidental
    neighbours often carry longer, more repetitive descriptions than the one
    terse sentence that actually answers the question: ``TURBIDITY → SSC``,
    whose description is the definition of the relationship, ranked 49th of
    TURBIDITY's 593 neighbours and was cut, while ``TURBIDITY → PORSUK STREAM``
    ranked first. So seed-adjacent neighbours are admitted unconditionally and
    the lexical ranking only decides the remainder.
    """
    anchored = {
        name: edges for name, edges in neighbours.items() if name in seed_keys
    }
    rest = sorted(
        ((name, edges) for name, edges in neighbours.items() if name not in anchored),
        key=lambda item: (-_best_edge_lexical(source, item[1], lexical), item[0]),
    )
    budget = max(0, MAX_NEIGHBOURS_PER_NODE - len(anchored))
    return {**anchored, **dict(rest[:budget])}


def expand(
    source: GraphSource,
    seeds: list[SeedLink],
    config: GraphRagConfig,
    lexical: dict[int, float] | None = None,
) -> list[tuple[list[str], list[Relation], float]]:
    """Bounded max-score BFS from every seed at once.

    Returns ``(nodes, edges, graph_score)`` triples. All seeds share one search
    because their paths can meet: the same chain discovered from two different
    seeds should surface once, at the higher of the two scores.

    A node with more neighbours than :data:`MAX_NEIGHBOURS_PER_NODE` keeps the
    ones the question is lexically closest to. The budget is not the interesting
    part — the *ordering* is. Taking the first N in file order is indistinguishable
    from choosing at random, and it is why a hub seed swallowed the record
    allowance before the next seed was expanded at all: every one of TURBIDITY's
    593 edges scored identically at that point, so the answer to "which of these
    does the question want" was decided by parquet row order. ``lexical`` is the
    only relevance signal available this early, and it is a good one — the
    inherited graph's descriptions *are* in the question's language.
    """
    depth = config.depth_for(source.source_id)
    counter = 0
    heap: list[tuple[float, int, str, tuple[str, ...], tuple[Relation, ...]]] = []
    best: dict[str, float] = {}

    for seed in seeds:
        best[seed.node_key] = max(best.get(seed.node_key, 0.0), seed.score)
        heap.append((-seed.score, counter, seed.node_key, (seed.node_key,), ()))
        counter += 1

    heapq.heapify(heap)
    seed_keys = {seed.node_key for seed in seeds}
    found: list[tuple[list[str], list[Relation], float]] = []
    # A safety valve, not a selector: with the per-node budget in place the
    # record count is bounded by (expanded nodes × budget), and doubling the
    # allowance keeps a legitimate run from tripping it. When it does trip it
    # truncates in heap order — strongest first — which is the only truncation
    # this search can justify.
    record_limit = config.max_paths * 4

    while heap:
        neg_score, _, node, node_path, edge_path = heapq.heappop(heap)
        score = -neg_score

        if len(edge_path) >= depth or score < config.path_min_score:
            if edge_path:
                found.append((list(node_path), list(edge_path), score))
            continue

        visited = set(node_path)
        neighbours = incident_edges(source, node)
        if len(neighbours) > MAX_NEIGHBOURS_PER_NODE:
            neighbours = _budget_neighbours(neighbours, seed_keys, source, lexical)
        for neighbour, edges in neighbours.items():
            if neighbour in visited:
                continue
            forward = edges[:MAX_PARALLEL_EDGES]
            # Parallel edges mean the same claim asserted more than once. Treat
            # that as weaker per-edge evidence, not stronger: a pair joined by
            # 40 descriptions is usually a hub, not 40 independent findings.
            edge_factor = 1.0 / (1.0 + math.log1p(len(edges)))
            new_score = score * config.hop_decay * edge_factor
            if new_score < config.path_min_score:
                continue

            # Record the edge *before* the pruning check. ``best`` decides
            # whether to expand through a node again — it must not decide
            # whether the edge exists. Pruning first would silently drop every
            # edge leading into a node that was already scored higher, and
            # those are precisely the strongest endpoints: for 沉积物 the direct
            # 农业活动 edge disappeared because AGRICULTURE was itself a seed.
            if len(found) < record_limit:
                found.append((list(node_path + (neighbour,)), list(edge_path + tuple(forward)), new_score))

            if new_score <= best.get(neighbour, 0.0):
                continue
            best[neighbour] = new_score
            counter += 1
            heapq.heappush(
                heap,
                (-new_score, counter, neighbour, node_path + (neighbour,), edge_path + tuple(forward)),
            )

        if len(found) >= record_limit:
            break

    return found


def seed_edges(source: GraphSource, seeds: list[SeedLink]) -> list[Relation]:
    """Every edge touching a seed.

    These are guaranteed a place in the prompt by :func:`select_paths`' caller,
    separately from path ranking. An edge from a seed is the most direct answer
    the graph can give, so it must not be crowded out of the result list by
    longer chains — but neither may it flood the *path* ranking, which is what
    happened when these were injected as candidate paths: on an 87-edge graph
    with 12 seeds, nearly every edge touches a seed, so the top-8 filled with
    one-hop pairs and no chain ever surfaced.
    """
    out: list[Relation] = []
    seen: set[tuple[str, str, str]] = set()
    for seed in seeds:
        for edges in incident_edges(source, seed.node_key).values():
            for edge in edges[:MAX_PARALLEL_EDGES]:
                if edge.key in seen:
                    continue
                seen.add(edge.key)
                out.append(edge)
    return out


def lexical_lookup(bundle: IndexBundle, source: GraphSource, query: str) -> dict[int, float]:
    """Position-indexed lexical scores, so a relation is one integer lookup.

    One vectorised pass over the whole index rather than a call per edge — the
    vectorizer is memoised, but a per-edge call would still be one matmul each.
    """
    if bundle.lexical is None:
        return {}
    scores = bundle.lexical.scores(query)
    out: dict[int, float] = {}
    for position in range(len(source.relations)):
        index = bundle.lexical.position(relation_doc_id(source.source_id, position))
        if index is not None:
            out[position] = float(scores[index])
    return out


def rank_by_lexical(
    bundle: IndexBundle,
    edges: list[Relation],
    query: str,
) -> list[Relation]:
    """Order edges by how well they match the question, best first.

    Needed for the edges that reach the prompt *without* competing in the path
    ranking — the ones touching a seed. They have no path score to sort by, and
    adjacency order is an accident of the file, so lexical relevance is the only
    honest ordering available. One vectorised pass per source, not per edge.
    """
    by_source: dict[str, list[Relation]] = {}
    for edge in edges:
        by_source.setdefault(edge.source.partition("::")[0], []).append(edge)

    scored: list[tuple[float, Relation]] = []
    for source_id, group in by_source.items():
        source = bundle.sources.get(source_id)
        if source is None:
            continue
        lookup = lexical_lookup(bundle, source, query)
        for edge in group:
            position = source.relation_positions.get(edge.key, -1)
            scored.append((lookup.get(position, 0.0), edge))

    scored.sort(key=lambda item: (-item[0], item[1].key))
    return [edge for _score, edge in scored]


def search_source(
    bundle: IndexBundle,
    source: GraphSource,
    seeds: list[SeedLink],
    query: str,
    config: GraphRagConfig,
    intent_type: str | None,
) -> list[PathCandidate]:
    """Every candidate path in one source, scored on the parts that do not
    depend on other sources. Struct is normalised later, across all of them."""
    if not seeds:
        return []

    # Lexical first: the traversal needs it to decide which of a hub's hundreds
    # of edges are worth carrying.
    lexical = lexical_lookup(bundle, source, query)
    raw = expand(source, seeds, config, lexical)
    seed_keys = {seed.node_key for seed in seeds}
    total_seeds = len(seed_keys)

    candidates: list[PathCandidate] = []
    for nodes, edges, graph_score in raw:
        if not edges:
            continue
        edge_scores = [
            lexical.get(source.relation_positions.get(edge.key, -1), 0.0) for edge in edges
        ]
        # A chain is as relevant as its strongest link, with the rest of the
        # chain as support — not as its average, which would punish a
        # three-hop path for containing two unremarkable connectors.
        lex = (
            0.7 * max(edge_scores) + 0.3 * (sum(edge_scores) / len(edge_scores))
            if edge_scores
            else 0.0
        )
        matched = len(set(nodes) & seed_keys)
        # Coverage saturates rather than running the full seed list. The seed
        # count is not a property of the question — a synonym group expands one
        # Chinese noun into a dozen English entities, and the per-source cap
        # then allows up to 24 — so dividing by it makes every path's coverage
        # a near-constant ~0.08 and the signal stops discriminating: the one
        # path that joins two named seeds scores the same as any hub edge that
        # happens to touch one. What is being asked is "does this chain account
        # for the question's entities", and two or three is the honest top of
        # that scale.
        cov = matched / max(1, min(total_seeds, COVERAGE_FULL))
        type_hit = 1.0 if intent_type and any(
            source.node_types.get(node) == intent_type for node in nodes
        ) else 0.0

        candidates.append(
            PathCandidate(
                source_id=source.source_id,
                nodes=nodes,
                edges=edges,
                graph_score=graph_score,
                lex=lex,
                cov=cov,
                type_hit=type_hit,
            )
        )
    return candidates


def fuse(candidates: list[PathCandidate], config: GraphRagConfig) -> list[PathCandidate]:
    """Combine the four signals and apply the source prior.

    ``struct`` is normalised against the strongest path *in this query* rather
    than against an absolute scale, because graph score is an accumulated decay
    product whose range depends on hop depth and seed score — a fixed scale
    would make it incomparable between a two-hop platform path and a one-hop
    inherited one.
    """
    if not candidates:
        return []

    peak = max(candidate.graph_score for candidate in candidates) or 1.0
    for candidate in candidates:
        struct = candidate.graph_score / peak
        score = (
            config.w_struct * struct
            + config.w_lex * candidate.lex
            + config.w_cov * candidate.cov
            + config.w_type * candidate.type_hit
        ) * config.prior_for(candidate.source_id)
        candidate.score = score
        candidate.score_parts = {
            "struct": struct,
            "lex": candidate.lex,
            "cov": candidate.cov,
            "type": candidate.type_hit,
        }
    return candidates


def dedupe(candidates: list[PathCandidate], config: GraphRagConfig) -> list[PathCandidate]:
    """Drop dominated paths, then collapse the same chain found twice.

    Domination is the interesting one: on a chain ``A→B→C→D`` the search also
    emits ``A→B→C``. Both are "correct", but the shorter one is a prefix of the
    longer and scores lower, so keeping it spends prompt budget saying the same
    thing twice.
    """
    candidates = sorted(candidates, key=lambda item: (-item.score, item.hops))
    kept: list[PathCandidate] = []
    for candidate in candidates:
        nodes = candidate.node_set()
        dominated = any(
            nodes <= other.node_set() and candidate.score <= other.score for other in kept
        )
        if dominated:
            continue
        kept.append(candidate)

    seen: dict[frozenset, int] = {}
    unique: list[PathCandidate] = []
    for candidate in kept:
        signature = candidate.signature()
        if signature in seen:
            continue
        seen[signature] = len(unique)
        unique.append(candidate)
    return unique


def _interleave_by_source(ranked: list[PathCandidate]) -> list[PathCandidate]:
    """Round-robin ``ranked`` between sources, preserving each source's order.

    Applied *before* the ``top_k`` cut, which is the whole point: the two
    sources hold different material, and the ``top_k`` window is where a
    question's evidence is either admitted or lost. Letting the sort decide
    means the larger graph decides — the inherited source has 18k edges against
    the platform's 87, so a question that links into both fills most of the
    window with inherited edges and pushes the platform's own answer, which is
    often the direct one, past the cut. A source that runs out simply stops
    contributing, so a single-source question still fills every slot.
    """
    groups: dict[str, list[PathCandidate]] = {}
    for candidate in ranked:
        groups.setdefault(candidate.source_id, []).append(candidate)

    out: list[PathCandidate] = []
    order = sorted(groups)
    while order:
        for source_id in list(order):
            group = groups[source_id]
            if not group:
                order.remove(source_id)
                continue
            out.append(group.pop(0))
    return out


def select_paths(
    candidates: list[PathCandidate],
    config: GraphRagConfig,
) -> list[PathCandidate]:
    """Top ``top_k`` paths above the final threshold, strongest first.

    Selection is capped **per anchor** — the seed each path grew from. Without
    that cap one high-scoring seed owns the whole result list with its own
    one-hop neighbours, and the multi-hop chains the search exists to find never
    reach the prompt.
    """
    ranked = _interleave_by_source(
        sorted(
            (item for item in candidates if item.score >= config.final_min_score),
            key=lambda item: (-item.score, item.hops, -item.lex),
        )
    )

    per_anchor: dict[str, int] = {}
    selected: list[PathCandidate] = []
    overflow: list[PathCandidate] = []
    for candidate in ranked:
        anchor = candidate.nodes[0] if candidate.nodes else ""
        if per_anchor.get(anchor, 0) >= config.paths_per_seed:
            overflow.append(candidate)
            continue
        per_anchor[anchor] = per_anchor.get(anchor, 0) + 1
        selected.append(candidate)
        if len(selected) >= config.top_k:
            return selected

    if selected:
        return selected

    # Only when the cap left nothing at all — a graph whose every path grows
    # from one seed. Falling back more eagerly would quietly undo the cap.
    return overflow[: config.top_k]


def path_relations(paths: list[PathCandidate], config: GraphRagConfig) -> list[Relation]:
    """The distinct relations the prompt will carry, capped at ``max_relations``.

    Ordered by the rank of the path each came from, so the cap drops the
    weakest path's edges rather than an arbitrary subset.
    """
    out: list[Relation] = []
    seen: set[tuple[str, str, str]] = set()
    for path in paths:
        for edge in path.edges:
            if edge.key in seen:
                continue
            seen.add(edge.key)
            out.append(edge)
            if len(out) >= config.max_relations:
                return out
    return out


def attach_chunks(
    bundle: IndexBundle,
    relations: list[Relation],
    config: GraphRagConfig,
) -> list[dict[str, Any]]:
    """Resolve each relation back to the source text it was extracted from.

    Returns ``[]`` when the index has no chunk level — which is permanent for
    the shipped baseline and for the inherited parquet. The caller reports that
    as a capability, not as an error.
    """
    out: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for relation in relations:
        source_id = relation.source.partition("::")[0]
        for item in bundle.occurrence_chunks(
            source_id, relation.key, config.max_chunks_per_relation
        ):
            chunk: Chunk = item["chunk"]
            excerpt = chunk.text[: config.chunk_excerpt_chars]
            if chunk.chunk_id in seen:
                position = seen[chunk.chunk_id]
                marker = [
                    [relation.display_source, relation.relation, relation.display_target]
                ]
                if marker[0] not in out[position]["used_by_relations"]:
                    out[position]["used_by_relations"].extend(marker)
                continue
            seen[chunk.chunk_id] = len(out)
            out.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "source_file": chunk.source_file,
                    "ordinal": chunk.ordinal,
                    "excerpt": excerpt,
                    "truncated": len(chunk.text) > len(excerpt),
                    "used_by_relations": [
                        [relation.display_source, relation.relation, relation.display_target]
                    ],
                }
            )
    return out
