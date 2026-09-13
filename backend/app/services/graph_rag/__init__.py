"""GraphRAG retrieval over the platform's knowledge graphs.

Dependency direction is strictly one-way: ``kg_service`` imports from this
package, never the reverse. ``KnowledgeGraphService.qa()`` delegates here, so a
back-import would close a cycle — including from ``pipeline``.

The package is pure-CPU and synchronous. Callers on an ``async def`` route must
wrap entry points in ``fastapi.concurrency.run_in_threadpool``.

Layout:

* :mod:`lexicon` — curated term lists (moved out of ``kg_service``), the
  synonym/related/bilingual groups the entity linker resolves against.
* :mod:`config` — every tunable in one frozen dataclass.
* :mod:`index` — the multi-source index bundle, its lexical retriever, and the
  cache key derived caches hang off.
* :mod:`sources` — loaders for the platform graph and the inherited GraphRAG
  parquet.
* :mod:`entity_link` — question text to graph seeds.
* :mod:`local_search` — seeds to scored multi-hop paths.
* :mod:`global_search` — communities and their (cached) summaries.
* :mod:`router` — question to ``local`` / ``global`` / ``hybrid`` / ``none``.
* :mod:`answering` — grounded prompt, citation parsing and validation.
* :mod:`pipeline` — the ``search()`` entry point that ties them together.
"""

from __future__ import annotations

from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.index import IndexBundle, load_index
from backend.app.services.graph_rag.sources import resolve_sources

__all__ = [
    "GraphRagConfig",
    "IndexBundle",
    "load_index",
    "resolve_sources",
]


def search(*args, **kwargs):
    """Deferred re-export of :func:`graph_rag.pipeline.search`.

    Imported lazily so that importing ``graph_rag`` (which ``kg_service`` does
    at module load, for the lexicon) does not pull in the whole retrieval stack
    for callers that only want the term lists.
    """
    from backend.app.services.graph_rag.pipeline import search as _search

    return _search(*args, **kwargs)
