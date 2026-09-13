"""Question -> ``local`` / ``global`` / ``hybrid`` / ``none``.

A small additive cue model, deliberately not an LLM call. Two reasons:

* **Cost and latency.** ``hybrid`` is cheap to *execute* — it computes both
  candidate sets and still pays for exactly one answer call — whereas a routing
  LLM call would double the per-question latency and spend, and would make the
  evaluation non-deterministic.
* **The uncertainty band already maps to ``hybrid``.** Anything ambiguous runs
  both retrievals, so a misroute inside that band costs nothing. A router only
  needs to be right about the clear cases.

:func:`classify_with_llm` is implemented and off by default
(``WATEREXPERT_GRAPH_RAG_LLM_ROUTER``), for when the corpus grows enough that
the heuristics stop separating.
"""

from __future__ import annotations

import logging
import re

from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.entity_link import SeedLink
from backend.app.services.graph_rag.index import IndexBundle

logger = logging.getLogger(__name__)

LOCAL = "local"
GLOBAL = "global"
HYBRID = "hybrid"
NONE = "none"

#: Wording that asks about the corpus rather than about a specific entity.
GLOBAL_CUES = (
    "总体", "整体", "主要", "概述", "总结", "概况", "有哪些", "包括哪些",
    "研究现状", "综述", "主要发现", "普遍", "一般规律",
    "overall", "summar", "main ", "overview", "in general", "broadly",
)

#: Subject-matter topics that are answered by a survey rather than an edge.
TOPIC_TERMS = (
    "影响因素", "监测方法", "治理措施", "水质因子", "环境因子", "驱动因素",
)

#: Verbs that assert a relationship, so the question is about a specific edge.
RELATION_TERMS = (
    "影响", "导致", "关系", "相关", "引起", "造成", "驱动", "监测", "反演",
    "改善", "降低", "增加", "affect", "cause", "relate", "impact", "drive",
)

_SHORT_QUESTION_CHARS = 24
_LONG_QUESTION_CHARS = 40
_STRONG_SEED_SCORE = 0.80
_MANY_SEEDS = 4
_MANY_COMMUNITIES = 3

_SHAPE_CUES = re.compile(r"(如何|为什么|为何|是否|多少|怎样|怎么|哪些|what|why|how)")


def score_local(question: str, seeds: list[SeedLink]) -> float:
    score = 0.0
    if seeds and seeds[0].score >= _STRONG_SEED_SCORE:
        score += 1.0
    if any(term in question.lower() for term in RELATION_TERMS) and seeds:
        score += 1.0
    if len(question) < _SHORT_QUESTION_CHARS:
        score += 0.5
    if _SHAPE_CUES.search(question):
        score += 0.5
    return score


def score_global(
    question: str,
    seeds: list[SeedLink],
    *,
    community_count: int = 0,
) -> float:
    lowered = question.lower()
    score = 0.0
    if any(cue in lowered for cue in GLOBAL_CUES):
        score += 1.0
    if len(question) > _LONG_QUESTION_CHARS:
        score += 1.0
    if sum(1 for term in TOPIC_TERMS if term in question) >= 2:
        score += 1.0
    if community_count and len(seeds) >= _MANY_SEEDS:
        sources = {seed.source_id for seed in seeds}
        if len(sources) >= 2 or community_count >= _MANY_COMMUNITIES:
            score += 1.0
    return score


def route(
    question: str,
    seeds: list[SeedLink],
    bundle: IndexBundle,
    config: GraphRagConfig,
    *,
    community_count: int = 0,
) -> tuple[str, dict[str, float], list[str]]:
    """Return ``(mode, scores, notes)``.

    ``notes`` records why the mode was overridden, so a surprising routing
    decision is visible in the response instead of having to be re-derived.
    """
    notes: list[str] = []

    if bundle.is_empty:
        return NONE, {"local": 0.0, "global": 0.0}, ["索引为空。"]

    if not seeds:
        # No entity in the question reached the graph. The plan scored this as
        # evidence *for* global — "no specific entity, so it must be a survey".
        # Measurement says otherwise on this corpus: every genuine survey
        # question here does link (清澈度 → TRANSPARENCY at 0.90), while the
        # questions that link nothing are the ones the graph has nothing to say
        # about. A global cue still routes to global, which will find no
        # community with a named member and refuse — visible, rather than
        # answered from the least-dissimilar community.
        if any(cue in question.lower() for cue in GLOBAL_CUES):
            notes.append("问题未命中图谱实体，但含全局线索；尝试全局检索。")
            return GLOBAL, {"local": 0.0, "global": 1.0}, notes
        notes.append("问题未命中任何图谱实体，判定为图谱外问题。")
        return NONE, {"local": 0.0, "global": 0.0}, notes

    global_usable = config.communities_enabled and community_count >= 2
    if not global_usable:
        notes.append("社区能力不可用，回退到 local。")
        return LOCAL, {"local": score_local(question, seeds), "global": 0.0}, notes

    local_score = score_local(question, seeds)
    global_score = score_global(question, seeds, community_count=community_count)

    if abs(global_score - local_score) < config.router_hybrid_margin:
        return HYBRID, {"local": local_score, "global": global_score}, notes
    if global_score > local_score:
        return GLOBAL, {"local": local_score, "global": global_score}, notes
    return LOCAL, {"local": local_score, "global": global_score}, notes


_SYSTEM_PROMPT = """你在为检索路由器分类一个问题，只输出 JSON。

可选类别：
- local：问题指向具体实体或实体之间的关系（如"风如何影响浊度"）
- global：问题要求对整个语料做概括（如"主要有哪些影响因素"）
- none：问题与水体清澈度知识图谱无关

输出格式：{"mode": "local|global|none"}"""


def classify_with_llm(question: str) -> str | None:
    """LLM-based routing, kept off by default.

    Returns ``None`` rather than a guess when the model is unavailable or
    answers something unrecognised — the caller falls back to the heuristic
    scores, which is the same behaviour as having the flag off.
    """
    from backend.app.services.kg_llm import call_llm, is_llm_configured

    if not is_llm_configured():
        return None
    try:
        raw = call_llm(question, system_prompt=_SYSTEM_PROMPT, temperature=0.0)
    except Exception as exc:  # noqa: BLE001 — routing must never fail a request
        logger.warning("LLM router failed, falling back to heuristics: %s", exc)
        return None

    match = re.search(r'"(local|global|none)"', raw or "")
    return match.group(1) if match else None
