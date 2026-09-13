"""Grounded prompt, citation parsing, and citation validation.

The materials are rendered as **numbered, individually addressable blocks** and
never as prose. That is what makes validation possible: the model is required to
end each factual sentence with ``[关系N]``, so a marker that does not exist in
the materials is mechanically detectable rather than a judgement call.

The fallback renderer emits the *same* markers as the LLM path. A deployment
with no API key therefore exercises the same UI, the same citation panel and the
same evaluation code path as one with a key — it simply reports
``stats.llm_called = false``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.app.services.graph_rag.index import Relation
from backend.app.services.graph_rag.local_search import PathCandidate

MARKER_RE = re.compile(r"\[(关系|分块|社区)(\d+)\]")
SENTENCE_SPLIT = re.compile(r"[。！？!?\n]+")

#: Marker prefix -> the ``citations`` entry's ``kind``.
MARKER_KINDS = {"关系": "relation", "分块": "chunk", "社区": "community"}

#: A "factual sentence" must be at least this long; shorter fragments are
#: headings, list bullets and connectives, which carry no claim to ground.
MIN_SENTENCE_CHARS = 8

_SYSTEM_PROMPT = """你是水体清澈度领域的知识图谱问答助手。你只能依据下面给出的编号材料回答。

规则：
1. 只能使用给出的编号材料；不要使用材料之外的任何知识。
2. 每个事实句的末尾必须标注来源标记，形如 [关系1]、[分块2]、[社区1]；每句至少一个。
3. 材料不足以回答时，回答"当前知识图谱中没有足够信息回答该问题"，并说明缺什么；不要用常识补充。
4. 不要罗列三元组。若材料构成因果链，请把它组织成通顺的因果叙述。
5. 材料之间互相矛盾时，并列陈述并各自标注来源。
6. 只输出 JSON，不要输出其他文字。

输出格式：
{"answer": "……", "used_citations": ["关系1", "关系2"], "insufficient": false}"""


def source_of(relation: Relation) -> str:
    return relation.source_id


def _sentences(text: str) -> list[str]:
    """Split prose into sentences and put the punctuation back.

    ``SENTENCE_SPLIT`` consumes its delimiter, so a naive ``split`` loses the
    full stops; rejoining with one restores readable output while keeping the
    same boundaries :func:`validate_citations` measures against.
    """
    return [part.strip() for part in SENTENCE_SPLIT.split(text) if part.strip()]


def _mark_each(text: str, marker: str) -> str:
    """Put ``marker`` at the end of every sentence of ``text``.

    An edge's description, a community summary and a 400-character chunk excerpt
    are each a *single* citation that happens to contain several sentences.
    Marking only the block's first sentence would have :func:`validate_citations`
    report a fully-anchored answer as mostly unsupported — the measure would be
    reporting prose length, not grounding.
    """
    parts = _sentences(text)
    if not parts:
        return text.strip()
    return " ".join(f"{part} {marker}" for part in parts)


def _is_lead_in(sentence: str) -> bool:
    """A heading, not a claim. ``相关图谱关系：`` introduces material rather than
    asserting anything, so counting it as an unsupported sentence would punish an
    answer for being well organised."""
    return sentence.strip().endswith(("：", ":"))


def build_materials(
    bundle: Any,
    paths: list[PathCandidate],
    relations: list[Relation],
    chunks: list[dict[str, Any]],
    communities: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
    """Render the numbered blocks and the citation index that explains them.

    Returns ``(material_text, citations, marker_numbers)``. The citations list is
    what the UI renders and what :func:`validate_citations` checks against.
    """
    lines: list[str] = []
    citations: list[dict[str, Any]] = []
    marker_numbers = {"关系": 0, "分块": 0, "社区": 0}

    for relation in relations:
        marker_numbers["关系"] += 1
        marker = f"关系{marker_numbers['关系']}"
        source_id = source_of(relation)
        source = bundle.sources.get(source_id)
        # Two different things used to share the name ``label``, and the second
        # assignment silently won: the source name was overwritten by the word
        # "证据"/"关系描述" before the ``来源:`` line and ``source_label`` read it.
        # The prompt therefore told the model every edge came from a file called
        # "关系描述", and every citation reported that as its graph. Distinct
        # names, because they are distinct facts.
        source_label = source.label if source is not None else source_id
        lines.append(f"[{marker}] {relation.display()}")
        if relation.evidence:
            # Labelled edge: the evidence supports the label. Unlabelled edge:
            # the description *is* the relation, so say so rather than calling it
            # evidence for a label that does not exist.
            evidence_label = "证据" if relation.relation else "关系描述"
            lines.append(f"  {evidence_label}: {relation.evidence}")
        origin = relation.source_file or "未知来源"
        lines.append(f"  来源: {origin}（{source_label}）")
        citations.append(
            {
                "marker": f"[{marker}]",
                "kind": "relation",
                "source_id": source_id,
                "source_label": source_label,
                **relation.as_dict(),
            }
        )

    for chunk in chunks:
        marker_numbers["分块"] += 1
        marker = f"分块{marker_numbers['分块']}"
        lines.append(
            f"[{marker}] {chunk['chunk_id']}（来源 {chunk.get('source_file') or '未知'}）"
            f"：「{chunk['excerpt']}」"
        )
        citations.append(
            {
                "marker": f"[{marker}]",
                "kind": "chunk",
                "chunk_id": chunk["chunk_id"],
                "source_file": chunk.get("source_file", ""),
            }
        )

    for community in communities:
        marker_numbers["社区"] += 1
        marker = f"社区{marker_numbers['社区']}"
        nodes = "、".join(str(name) for name in community.get("nodes", [])[:12])
        lines.append(f"[{marker}] {community['community_id']}（节点：{nodes}）：{community.get('summary', '')}")
        citations.append(
            {
                "marker": f"[{marker}]",
                "kind": "community",
                "community_id": community["community_id"],
                "source_id": community.get("source_id", ""),
                "size": community.get("size", 0),
                "summary_mode": community.get("summary_mode", "extractive"),
            }
        )

    return "\n".join(lines), citations, marker_numbers


def build_grounded_prompt(question: str, materials: str) -> str:
    return f"""问题：{question}

编号材料：
{materials}

请依据上述编号材料回答，并按要求的 JSON 格式输出。"""


def parse_answer_json(raw: str) -> dict[str, Any]:
    """Parse the model's JSON, tolerating prose or a code fence around it."""
    if not raw:
        return {}
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return {}
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def validate_citations(
    answer: str,
    known_markers: set[str],
    *,
    insufficient: bool = False,
) -> dict[str, Any]:
    """Measure how well the answer is anchored to the materials.

    ``citation_validity`` is the share of markers that resolve; a marker the
    model invented lands in ``hallucinated_markers`` and is stripped from the
    answer rather than being displayed as if it were a source.

    ``groundedness`` is the share of factual sentences carrying a valid marker.
    It is the more useful number of the two: an answer can cite only real
    markers and still leave half its claims unsupported.
    """
    markers = [f"[{kind}{number}]" for kind, number in MARKER_RE.findall(answer or "")]
    hallucinated: list[str] = []
    kept: list[str] = []
    for marker in markers:
        if marker in known_markers:
            kept.append(marker)
        elif marker not in hallucinated:
            hallucinated.append(marker)

    cleaned = answer or ""
    for marker in hallucinated:
        cleaned = cleaned.replace(marker, "")

    if not markers:
        # Refusing to answer is a valid, fully grounded outcome — there is
        # nothing claimed, so there is nothing unsupported.
        validity = 1.0 if insufficient else 0.0
    else:
        validity = len(kept) / len(markers)

    sentences = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT.split(cleaned)
        if len(sentence.strip()) >= MIN_SENTENCE_CHARS and not _is_lead_in(sentence)
    ]
    grounded = sum(1 for sentence in sentences if MARKER_RE.search(sentence))
    groundedness = (grounded / len(sentences)) if sentences else (1.0 if insufficient else 0.0)

    return {
        "citation_validity": round(validity, 4),
        "groundedness": round(groundedness, 4),
        "hallucinated_markers": hallucinated,
        "answer": cleaned.strip(),
        "used_markers": kept,
    }


def fallback_answer(
    paths: list[PathCandidate],
    relations: list[Relation],
    chunks: list[dict[str, Any]],
    communities: list[dict[str, Any]],
    *,
    reason: str = "",
) -> str:
    """Deterministic grounded rendering, used whenever the model is unavailable.

    Emits the same ``[关系N]`` markers as the LLM path so that everything
    downstream — the UI's citation panel, the evaluation harness — behaves
    identically whether or not a key is configured.
    """
    lines: list[str] = []

    if reason:
        lines.append(reason)
        lines.append("")

    if not relations and not communities:
        lines.append("当前知识图谱中没有检索到与该问题相关的关系或社区。")
        return "\n".join(lines)

    lines.append("依据当前知识图谱检索到的材料：")
    lines.append("")

    for index, relation in enumerate(relations, start=1):
        marker = f"[关系{index}]"
        lines.append(f"{index}. {relation.display()} {marker}")
        if relation.evidence:
            label = "证据" if relation.relation else "关系描述"
            lines.append(f"   {label}：{_mark_each(relation.evidence, marker)}")
        lines.append("")

    if paths:
        # Each chain is annotated with the markers of the relations it is made
        # of. A chain is not a new claim — it is the same cited edges, shown in
        # the order they connect — so leaving it unmarked would report a
        # well-organised answer as half-unsupported.
        marker_of = {relation.key: f"[关系{index}]" for index, relation in enumerate(relations, 1)}
        chains = []
        for path in paths[:3]:
            if not path.edges:
                continue
            # Walk the chain node by node: the first edge's source, then every
            # edge's target. Alternating source/target by edge index instead —
            # which is what this did — renders a one-edge path as a lone node
            # and a two-edge path as source, target, source.
            # The edge label goes in as an arrow, matching ``Relation.display``.
            # It used to be bracketed — ``[导致]``, ``[相关]`` — which is the
            # exact shape of a citation marker while resolving as neither
            # ``MARKER_RE`` nor ``CITATION_RE``. The result was text that looked
            # clickable to a reader and counted as uncited to the validator. The
            # real markers are appended below; this never needed to be one.
            display = " ".join(
                [path.edges[0].display_source]
                + [
                    f"--{edge.relation or '相关'}--> {edge.display_target}"
                    for edge in path.edges
                ]
            )
            if not display:
                continue
            markers = "".join(
                dict.fromkeys(marker_of[edge.key] for edge in path.edges if edge.key in marker_of)
            )
            chains.append(f"- {display} {markers}".rstrip())
        if chains:
            lines.append("检索到的关联链路：")
            lines.extend(chains)
            lines.append("")

    if chunks:
        lines.append("可用原文片段：")
        for index, chunk in enumerate(chunks, start=1):
            lines.append(
                f"[分块{index}] {chunk['chunk_id']}："
                + _mark_each(str(chunk.get("excerpt") or ""), f"[分块{index}]")
            )
        lines.append("")

    if communities:
        lines.append("相关社区摘要：")
        for index, community in enumerate(communities, start=1):
            lines.append(
                f"[社区{index}] {community.get('community_id', '')}"
                f"（节点：{'、'.join(str(name) for name in (community.get('nodes') or [])[:12])}）："
            )
            lines.append(
                _mark_each(str(community.get("summary") or ""), f"[社区{index}]")
            )
        lines.append("")

    return "\n".join(lines).strip()


def answer(
    question: str,
    materials: str,
    citations: list[dict[str, Any]],
    *,
    paths: list[PathCandidate],
    relations: list[Relation],
    chunks: list[dict[str, Any]],
    communities: list[dict[str, Any]],
    llm_configured: bool,
) -> tuple[str, dict[str, Any]]:
    """Produce the answer text plus its validation stats.

    Every failure mode — no key, a raising client, unparseable JSON — lands on
    the same deterministic renderer, so a model outage degrades the prose and
    nothing else.
    """
    known_markers = {item["marker"] for item in citations}

    if not llm_configured:
        text = fallback_answer(
            paths, relations, chunks, communities,
            reason="未配置大语言模型，以下为知识图谱检索结果：",
        )
        stats = validate_citations(text, known_markers, insufficient=not relations)
        return stats.pop("answer"), {**stats, "llm_called": False}

    from backend.app.services.kg_llm import call_llm

    try:
        raw = call_llm(
            build_grounded_prompt(question, materials),
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001 — a model outage degrades prose, not the answer
        text = fallback_answer(
            paths, relations, chunks, communities,
            reason=f"大模型调用失败（{exc}），以下为知识图谱检索结果：",
        )
        stats = validate_citations(text, known_markers, insufficient=not relations)
        return stats.pop("answer"), {**stats, "llm_called": False, "llm_error": str(exc)}

    payload = parse_answer_json(raw)
    if not payload.get("answer"):
        # The model answered outside the contract. Its prose is not citable, so
        # it is discarded rather than shown with unverifiable confidence.
        text = fallback_answer(
            paths, relations, chunks, communities,
            reason="大模型未按约定格式返回，以下为知识图谱检索结果：",
        )
        stats = validate_citations(text, known_markers, insufficient=not relations)
        return stats.pop("answer"), {**stats, "llm_called": True, "llm_unstructured": True}

    stats = validate_citations(
        str(payload.get("answer") or ""),
        known_markers,
        insufficient=bool(payload.get("insufficient")),
    )
    return stats.pop("answer"), {
        **stats,
        "llm_called": True,
        "insufficient": bool(payload.get("insufficient")),
    }
