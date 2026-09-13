"""GraphRAG tunables.

Deliberately *not* folded into :class:`backend.app.config.Settings`: that would
force every ``Settings(...)`` construction in the test suite to carry retrieval
tuning it does not care about. A standalone frozen dataclass with an
``from_env`` classmethod keeps the two concerns apart.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

PREFIX = "WATEREXPERT_GRAPH_RAG_"

#: Per-source expansion depth. The platform graph is small and sparse, so
#: multi-hop chains are the thing worth retrieving. The inherited graph has
#: 18k edges and hub nodes with degree ~600 — two hops from TURBIDITY reaches
#: most of the graph and buries the signal, while each of its edges already
#: carries a full natural-language description. One hop it is.
DEFAULT_HOP_DEPTH: dict[str, int] = {"platform": 2, "inherited": 1}

#: A modest prior so the user's own literature outranks the inherited graph
#: when both are equally relevant.
DEFAULT_SOURCE_PRIOR: dict[str, float] = {"platform": 1.0, "inherited": 0.85}

DEFAULT_SOURCES: tuple[str, ...] = ("platform", "inherited")


@dataclass(frozen=True)
class GraphRagConfig:
    # ---- sources ----------------------------------------------------------
    sources: tuple[str, ...] = DEFAULT_SOURCES
    source_prior: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_SOURCE_PRIOR))
    hop_depth: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_HOP_DEPTH))
    max_hop_depth: int = 3

    # ---- seeding ----------------------------------------------------------
    max_seeds: int = 12
    seed_min_score: float = 0.45

    # ---- path expansion ---------------------------------------------------
    hop_decay: float = 0.6
    max_paths: int = 200
    path_min_score: float = 0.15

    # ---- ranking ----------------------------------------------------------
    top_k: int = 8
    max_relations: int = 12
    #: How many selected paths may grow from the same seed. One seed with many
    #: weak neighbours would otherwise fill the whole list with its own one-hop
    #: edges and crowd out every multi-hop chain.
    paths_per_seed: int = 2
    final_min_score: float = 0.12
    w_struct: float = 0.35
    w_lex: float = 0.45
    w_cov: float = 0.15
    w_type: float = 0.05
    tfidf_ngram_max: int = 3

    # ---- communities ------------------------------------------------------
    communities_enabled: bool = True
    summaries_enabled: bool = True
    community_max_llm_calls: int = 12
    community_max_edges: int = 25
    #: Louvain's PRNG seed. Pinned so an unchanged graph partitions identically
    #: across runs — community ids are derived from the partition, and ids that
    #: shuffled between rebuilds would orphan every cached summary.
    community_seed: int = 0
    summary_max_chars: int = 600
    global_top_k: int = 3
    global_max_edges: int = 15

    # ---- routing ----------------------------------------------------------
    router_hybrid_margin: float = 1.0
    llm_router: bool = False

    # ---- chunks -----------------------------------------------------------
    chunk_excerpt_chars: int = 400
    max_chunks_per_relation: int = 2

    # ---- linking ----------------------------------------------------------
    evidence_aliases: bool = True
    #: Let the platform's own field vocabulary (``ingestion/schema_registry``)
    #: reach the graph's entity names — see ``platform_vocabulary``.
    platform_vocabulary: bool = True

    # ---- agent injection --------------------------------------------------
    agent_top_k: int = 5
    agent_context_max_chars: int = 1500

    # ---- startup ----------------------------------------------------------
    warmup_on_startup: bool = True

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> GraphRagConfig:
        """Build a config from the environment.

        ``environ`` exists so tests can pass a mapping instead of monkeypatching
        ``os.environ``. Unset or unparseable entries fall back to the defaults
        above rather than raising — a typo in a tuning knob must not take the
        service down.
        """
        env = os.environ if environ is None else environ

        def raw(name: str) -> str:
            return (env.get(PREFIX + name) or "").strip()

        def as_int(name: str, default: int) -> int:
            value = raw(name)
            if not value:
                return default
            try:
                return int(value)
            except ValueError:
                return default

        def as_float(name: str, default: float) -> float:
            value = raw(name)
            if not value:
                return default
            try:
                return float(value)
            except ValueError:
                return default

        def as_bool(name: str, default: bool) -> bool:
            value = raw(name).lower()
            if not value:
                return default
            return value not in {"0", "false", "no", "off"}

        def as_pair_map(name: str, default: Mapping[str, float]) -> dict[str, float]:
            """Parse ``platform=1.0,inherited=0.85``."""
            value = raw(name)
            if not value:
                return dict(default)
            parsed: dict[str, float] = {}
            for part in value.split(","):
                key, sep, item = part.partition("=")
                if not sep:
                    continue
                try:
                    parsed[key.strip()] = float(item)
                except ValueError:
                    continue
            return parsed or dict(default)

        sources_raw = raw("SOURCES")
        sources = (
            tuple(part.strip() for part in sources_raw.split(",") if part.strip())
            if sources_raw
            else DEFAULT_SOURCES
        )

        hop_depth = {
            key: int(value) for key, value in as_pair_map("HOP_DEPTH", DEFAULT_HOP_DEPTH).items()
        }

        return cls(
            sources=sources,
            source_prior=as_pair_map("SOURCE_PRIOR", DEFAULT_SOURCE_PRIOR),
            hop_depth=hop_depth,
            max_hop_depth=as_int("MAX_HOP_DEPTH", 3),
            max_seeds=as_int("MAX_SEEDS", 12),
            seed_min_score=as_float("SEED_MIN_SCORE", 0.45),
            hop_decay=as_float("HOP_DECAY", 0.6),
            max_paths=as_int("MAX_PATHS", 200),
            path_min_score=as_float("PATH_MIN_SCORE", 0.15),
            top_k=as_int("TOP_K", 8),
            max_relations=as_int("MAX_RELATIONS", 12),
            paths_per_seed=as_int("PATHS_PER_SEED", 2),
            final_min_score=as_float("FINAL_MIN_SCORE", 0.12),
            w_struct=as_float("W_STRUCT", 0.35),
            w_lex=as_float("W_LEX", 0.45),
            w_cov=as_float("W_COV", 0.15),
            w_type=as_float("W_TYPE", 0.05),
            tfidf_ngram_max=as_int("TFIDF_NGRAM_MAX", 3),
            communities_enabled=as_bool("COMMUNITIES_ENABLED", True),
            summaries_enabled=as_bool("COMMUNITY_SUMMARIES", True),
            community_max_llm_calls=as_int("COMMUNITY_MAX_LLM_CALLS", 12),
            community_max_edges=as_int("COMMUNITY_MAX_EDGES", 25),
            community_seed=as_int("COMMUNITY_SEED", 0),
            summary_max_chars=as_int("SUMMARY_MAX_CHARS", 600),
            global_top_k=as_int("GLOBAL_TOP_K", 3),
            global_max_edges=as_int("GLOBAL_MAX_EDGES", 15),
            router_hybrid_margin=as_float("ROUTER_HYBRID_MARGIN", 1.0),
            llm_router=as_bool("LLM_ROUTER", False),
            chunk_excerpt_chars=as_int("CHUNK_EXCERPT_CHARS", 400),
            max_chunks_per_relation=as_int("MAX_CHUNKS_PER_REL", 2),
            evidence_aliases=as_bool("EVIDENCE_ALIASES", True),
            platform_vocabulary=as_bool("PLATFORM_VOCABULARY", True),
            agent_top_k=as_int("AGENT_TOP_K", 5),
            agent_context_max_chars=as_int("AGENT_MAX_CHARS", 1500),
            warmup_on_startup=as_bool("WARMUP", True),
        )

    def with_overrides(self, **changes: object) -> GraphRagConfig:
        """Copy with ``changes`` applied — keeps the frozen dataclass ergonomic."""
        return replace(self, **changes)

    def depth_for(self, source_id: str) -> int:
        depth = int(self.hop_depth.get(source_id, 1))
        return max(1, min(depth, self.max_hop_depth))

    def prior_for(self, source_id: str) -> float:
        return float(self.source_prior.get(source_id, 1.0))
