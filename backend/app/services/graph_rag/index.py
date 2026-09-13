"""The multi-source GraphRAG index.

Two logical sources are indexed side by side and never joined by fabricated
edges — fusion happens in the ranking layer, not in the graph:

``platform``
    The graph the user built from their own literature (``var/knowledge_graph``)
    or, failing that, the committed baseline (``outputs/knowledge_graph``).
    Chinese entities, Chinese/English evidence, and — after a rebuild — chunk
    provenance.

``inherited``
    ``create_final_relationships.parquet``, a Microsoft GraphRAG export with
    18,157 edges over 10,567 entities. Its entity names are UPPERCASE ENGLISH
    and it has no relation-type column: the edge's ``description`` *is* the
    relation, in Chinese. That is why lexical matching works across languages
    here without a translation model — a Chinese question matches the Chinese
    description, and the matched edge hands us its endpoints as graph seeds.

Node keys are ``f"{source_id}::{name}"`` so the two sources cannot collide.
``entity_id`` (``E0001``…) is never a key: ``save_kg`` renumbers it on every
rebuild.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

import networkx as nx

from backend.app.services.graph_rag.config import GraphRagConfig

logger = logging.getLogger(__name__)

INDEX_VERSION = 1
GRAPH_RAG_VERSION = "1"


def node_key(source_id: str, name: str) -> str:
    return f"{source_id}::{name}"


def split_node_key(key: str) -> tuple[str, str]:
    source_id, _, name = key.partition("::")
    return source_id, name


@dataclass(frozen=True)
class Relation:
    """One graph edge, normalised across both sources.

    ``source``/``target`` hold **namespaced node keys** (``platform::浊度``), so
    the two sources can never collide. Display and lexical text strip the
    prefix — it must not leak into n-grams or citations.
    """

    source: str
    target: str
    relation: str
    evidence: str
    source_type: str = "未知类型"
    target_type: str = "未知类型"
    source_file: str = ""
    chunk_id: str | None = None
    weight: float = 1.0
    rank: int = 0
    source_degree: int = 0
    target_degree: int = 0

    @property
    def display_source(self) -> str:
        return split_node_key(self.source)[1]

    @property
    def display_target(self) -> str:
        return split_node_key(self.target)[1]

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source, self.relation, self.target)

    def display(self) -> str:
        """The short form: endpoints, and the relation label when there is one.

        An unlabelled edge — every edge of the inherited graph, whose
        ``description`` *is* its relation — renders as ``A → B`` and leaves the
        description to be shown once, below, as the evidence. Inlining it into
        the arrow too would print the same paragraph twice in every prompt and
        every answer, and for a 600-character GraphRAG description that is not a
        cosmetic problem: it is most of the material budget spent on a duplicate.
        """
        if self.relation:
            return f"{self.display_source} --{self.relation}--> {self.display_target}"
        return f"{self.display_source} → {self.display_target}"

    def lexical_text(self) -> str:
        """The document this edge contributes to the lexical index.

        Deliberately includes *both* the entity names and the natural-language
        field: the names carry the exact-match signal, the evidence/description
        carries the paraphrase signal.
        """
        text = f"{self.display_source} {self.display_target} {self.relation} {self.evidence}"
        return " ".join(text.split())

    def as_dict(self) -> dict[str, Any]:
        """The shape the API has always returned for ``matched_relations``."""
        return {
            "source": self.display_source,
            "source_type": self.source_type,
            "relation": self.relation,
            "target": self.display_target,
            "target_type": self.target_type,
            "evidence": self.evidence,
            "source_file": self.source_file,
            "chunk_id": self.chunk_id,
        }


@dataclass
class Chunk:
    chunk_id: str
    source_file: str
    ordinal: int
    text: str
    char_start: int = 0
    char_end: int = 0

    @property
    def doc_id(self) -> str:
        return f"c#{self.chunk_id}"


@dataclass
class GraphSource:
    """One indexed graph, with everything that belongs to it."""

    source_id: str
    label: str
    provenance: str
    label_key: str = ""
    relations: list[Relation] = field(default_factory=list)
    graph: nx.MultiDiGraph = field(default_factory=nx.MultiDiGraph)
    undirected: nx.Graph = field(default_factory=nx.Graph)
    node_types: dict[str, str] = field(default_factory=dict)
    chunks: dict[str, Chunk] = field(default_factory=dict)
    #: relation key -> every pre-dedupe occurrence that produced it
    occurrences: dict[tuple[str, str, str], list[dict[str, Any]]] = field(default_factory=dict)
    #: relation key -> position in ``relations``
    relation_positions: dict[tuple[str, str, str], int] = field(default_factory=dict)
    communities: list[dict[str, Any]] | None = None

    @property
    def chunk_level(self) -> bool:
        return bool(self.chunks)

    @property
    def relation_count(self) -> int:
        return len(self.relations)

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def display_name(self, key: str) -> str:
        return split_node_key(key)[1]

    def degree(self, key: str) -> int:
        return int(self.graph.degree(key)) if key in self.graph else 0

    def relations_for(self, keys: Iterable[tuple[str, str, str]]) -> list[Relation]:
        out = []
        for key in keys:
            position = self.relation_positions.get(key)
            if position is not None:
                out.append(self.relations[position])
        return out

    def edges_between(self, left: str, right: str) -> list[Relation]:
        """All edges joining two node keys, in either direction."""
        out: list[Relation] = []
        for a, b in ((left, right), (right, left)):
            if not self.graph.has_edge(a, b):
                continue
            for data in self.graph[a][b].values():
                out.append(data["relation"])
        return out


class Retriever(Protocol):
    """Lexical scorer seam.

    ``LocalTfidf`` is the only implementation today. A dense
    ``SentenceTransformerRetriever`` would be one more class plus an optional
    dependency, with no call-site changes — deliberately left unimplemented.
    """

    def scores(self, query: str) -> Any:  # pragma: no cover - protocol
        ...


class LocalTfidf:
    """Character n-gram TF-IDF over heterogeneous short documents.

    ``analyzer="char_wb"`` needs no Chinese tokenizer — each CJK character is
    its own token — and it puts Chinese and English text in the *same* vector
    space, which is what lets a Chinese question match the platform graph's
    English evidence without translating anything.

    The vectorizer is fitted lazily on the first query and memoised: loading the
    index should not pay for a retrieval nobody asked for.
    """

    def __init__(self, ngram_max: int = 3) -> None:
        self._ngram_max = max(1, int(ngram_max))
        self._doc_ids: list[str] = []
        self._texts: list[str] = []
        self._positions: dict[str, int] = {}
        self._vectorizer: Any = None
        self._matrix: Any = None
        self._keep: Any = None
        self._lock = threading.Lock()

    def add(self, doc_id: str, text: str) -> None:
        if doc_id in self._positions:
            return
        self._positions[doc_id] = len(self._doc_ids)
        self._doc_ids.append(doc_id)
        self._texts.append(text or "")

    @property
    def doc_ids(self) -> list[str]:
        """Document ids, aligned row-for-row with :meth:`scores`."""
        return list(self._doc_ids)

    @property
    def size(self) -> int:
        return len(self._doc_ids)

    def position(self, doc_id: str) -> int | None:
        return self._positions.get(doc_id)

    def build(self) -> None:
        with self._lock:
            if self._matrix is not None or not self._texts:
                return
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer

            vectorizer = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(1, self._ngram_max),
                min_df=1,
                sublinear_tf=True,
                dtype=np.float32,
            )
            try:
                matrix = vectorizer.fit_transform(self._texts)
            except ValueError:
                # Empty vocabulary (e.g. every document blank) — leave the
                # index unusable-but-safe rather than raising into a request.
                logger.warning("GraphRAG lexical index has an empty vocabulary.")
                self._matrix = None
                self._vectorizer = None
                return

            # ``char_wb`` pads every word with a space, so the bare space is a
            # 1-gram of *every* document and every query. Left in, it puts a
            # constant floor under every score — enough, on a short document, to
            # swamp the real signal (a single-doc index scores an unrelated
            # query 0.47). Dropping the blank columns keeps "no lexical overlap"
            # scoring exactly zero, which is what lets the router and the
            # ``insufficient`` answer path detect that nothing matched.
            vocabulary = vectorizer.get_feature_names_out()
            keep = np.array([bool(term.strip()) for term in vocabulary], dtype=bool)
            self._keep = keep
            if not keep.all():
                matrix = matrix[:, keep]

            self._matrix = matrix
            self._vectorizer = vectorizer

    def scores(self, query: str) -> Any:
        """Cosine-ish scores aligned with :attr:`doc_ids`; zeros if unusable."""
        import numpy as np

        self.build()
        if self._matrix is None or self._vectorizer is None:
            return np.zeros(len(self._doc_ids), dtype="float32")
        query_vector = self._vectorizer.transform([query or ""])
        if self._keep is not None and not self._keep.all():
            query_vector = query_vector[:, self._keep]
        return (self._matrix @ query_vector.T).toarray().ravel()

    def score_one(self, query: str, doc_id: str) -> float:
        position = self._positions.get(doc_id)
        if position is None:
            return 0.0
        return float(self.scores(query)[position])


@dataclass
class IndexBundle:
    sources: dict[str, GraphSource] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    lexical: LocalTfidf | None = None
    content_hash: str = ""
    index_version: int = INDEX_VERSION
    notes: list[str] = field(default_factory=list)

    # -- aggregate views ----------------------------------------------------
    @property
    def relation_count(self) -> int:
        return sum(source.relation_count for source in self.sources.values())

    @property
    def has_chunks(self) -> bool:
        return any(source.chunk_level for source in self.sources.values())

    @property
    def is_empty(self) -> bool:
        return self.relation_count == 0

    def all_chunks(self) -> dict[str, Chunk]:
        merged: dict[str, Chunk] = {}
        for source in self.sources.values():
            merged.update(source.chunks)
        return merged

    def relation(self, source_id: str, key: tuple[str, str, str]) -> Relation | None:
        source = self.sources.get(source_id)
        if source is None:
            return None
        position = source.relation_positions.get(key)
        return None if position is None else source.relations[position]

    def occurrence_chunks(
        self, source_id: str, key: tuple[str, str, str], limit: int
    ) -> list[dict[str, Any]]:
        """Chunk excerpts that produced ``key``, newest-proof and deduped."""
        source = self.sources.get(source_id)
        if source is None:
            return []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for occurrence in source.occurrences.get(key, []):
            chunk_id = occurrence.get("chunk_id")
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)
            chunk = source.chunks.get(chunk_id)
            if chunk is None:
                continue
            out.append({"chunk": chunk, "occurrence": occurrence})
            if len(out) >= limit:
                break
        return out

    def capabilities(self) -> dict[str, bool]:
        return {
            "chunk_level": self.has_chunks,
            "communities": any(source.communities for source in self.sources.values()),
            "citations": True,
        }

    def describe_sources(self) -> list[dict[str, Any]]:
        return [
            {
                "source_id": source.source_id,
                "label": source.label,
                "label_key": source.label_key,
                "provenance": source.provenance,
                "relation_count": source.relation_count,
                "node_count": source.node_count,
                "chunk_level": source.chunk_level,
            }
            for source in (self.sources[key] for key in self.order)
        ]


def build_graph(relations: list[Relation]) -> tuple[nx.MultiDiGraph, nx.Graph, dict[str, str]]:
    """Build the directed graph plus its undirected projection.

    Node types come from the relations' ``source_type``/``target_type`` — the
    authoritative copy — never from ``graph.json``, whose node ``type`` is
    last-write-wins and therefore unreliable.
    """
    graph = nx.MultiDiGraph()
    node_types: dict[str, str] = {}

    for index, relation in enumerate(relations):
        for name, entity_type in (
            (relation.source, relation.source_type),
            (relation.target, relation.target_type),
        ):
            if not name:
                continue
            # A real type beats the extractor's "未知类型" placeholder, whichever
            # order the rows arrive in.
            if name not in node_types or (
                node_types[name] == "未知类型" and entity_type != "未知类型"
            ):
                node_types[name] = entity_type or "未知类型"
            graph.add_node(name, label=split_node_key(name)[1], type=node_types[name])

        if not relation.source or not relation.target:
            continue
        graph.add_edge(
            relation.source,
            relation.target,
            key=index,
            relation=relation,
        )

    undirected = nx.Graph()
    for left, right, data in graph.edges(data=True):
        if undirected.has_edge(left, right):
            undirected[left][right]["count"] += 1
        else:
            undirected.add_edge(left, right, count=1)

    return graph, undirected, node_types


def content_hash(relations_path: Path | None, occurrences_path: Path | None) -> str:
    """Cache key for derived artifacts. Changes whenever the graph changes."""
    digest = hashlib.sha1()
    for path in (relations_path, occurrences_path):
        if path is not None and path.exists():
            try:
                digest.update(path.read_bytes())
            except OSError:  # pragma: no cover - unreadable file is treated as absent
                continue
    return "sha1:" + digest.hexdigest()


def read_chunks(path: Path | None) -> dict[str, Chunk]:
    if path is None or not path.exists():
        return {}
    chunks: dict[str, Chunk] = {}
    for line in _read_jsonl(path):
        chunk_id = str(line.get("chunk_id") or "").strip()
        if not chunk_id:
            continue
        chunks[chunk_id] = Chunk(
            chunk_id=chunk_id,
            source_file=str(line.get("source_file") or ""),
            ordinal=int(line.get("ordinal") or 0),
            text=str(line.get("text") or ""),
            char_start=int(line.get("char_start") or 0),
            char_end=int(line.get("char_end") or 0),
        )
    return chunks


def read_occurrences(path: Path | None) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    if path is None or not path.exists():
        return {}
    occurrences: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for line in _read_jsonl(path):
        key = (
            str(line.get("source") or ""),
            str(line.get("relation") or ""),
            str(line.get("target") or ""),
        )
        if not key[0] or not key[2]:
            continue
        occurrences.setdefault(key, []).append(line)
    return occurrences


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def build_lexical_index(sources: Iterable[GraphSource], config: GraphRagConfig) -> LocalTfidf:
    """One vector space over every source's edges, chunks and community summaries.

    A single space is what makes scores comparable across sources; the source
    prior is applied later, at ranking time.
    """
    lexical = LocalTfidf(ngram_max=config.tfidf_ngram_max)
    for source in sources:
        for position, relation in enumerate(source.relations):
            lexical.add(relation_doc_id(source.source_id, position), relation.lexical_text())
        for chunk in source.chunks.values():
            lexical.add(chunk.doc_id, chunk.text)
        for community in source.communities or []:
            community_id = str(community.get("community_id") or "")
            if community_id:
                lexical.add(
                    community_doc_id(community_id),
                    community_lexical_text(community),
                )
    return lexical


def relation_doc_id(source_id: str, position: int) -> str:
    return f"r#{source_id}#{position}"


def community_doc_id(community_id: str) -> str:
    return f"g#{community_id}"


def community_lexical_text(community: dict[str, Any]) -> str:
    nodes = " ".join(str(name) for name in (community.get("nodes") or [])[:60])
    summary = str(community.get("summary") or "")
    return f"{summary} {nodes}".strip()


def load_index(
    sources: list[GraphSource],
    *,
    config: GraphRagConfig | None = None,
    content_hash_value: str = "",
) -> IndexBundle:
    """Assemble a bundle from already-loaded sources."""
    config = config or GraphRagConfig()
    bundle = IndexBundle(
        sources={source.source_id: source for source in sources},
        order=[source.source_id for source in sources],
        content_hash=content_hash_value,
    )
    bundle.lexical = build_lexical_index(sources, config)

    if not bundle.has_chunks:
        bundle.notes.append(
            "无分块级数据：引用仅到关系与来源文件。平台基线图谱的源文本已不可恢复，"
            "继承图谱也未导出 text_units。"
        )
    return bundle
