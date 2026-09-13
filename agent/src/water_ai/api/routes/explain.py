"""Explanation generation route - provides case-based reasoning and textual analysis."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...data.case_library import cases_for, describe
from ..schemas import KnowledgeContext

router = APIRouter(prefix="/api", tags=["explain"])


def _find_best_cases(scenario: str, state: dict, top_k: int = 2) -> list[dict[str, Any]]:
    """The closest cases this scenario has, widening to the library if it has none.

    The widening is this route's own long-standing behaviour and belongs to it
    rather than to the library, which is why it is requested explicitly here and
    refused by the knowledge base — see :func:`~...case_library.cases_for`.
    """
    return cases_for(scenario, state, top_k=top_k, fallback_to_all=True)


def _knowledge_section(context: KnowledgeContext | None) -> list[str]:
    """Render the platform's retrieved edges as an explanation section.

    This route never ran the orchestrator, so before now there was nowhere for
    retrieved evidence to go: the platform would have sent it, the payload
    reader would have dropped it, and the page would have looked identical.
    Rendering it here is what makes the injection observable rather than
    merely transmitted.

    Each edge names the graph it came from. The two graphs are not equals —
    one is the user's own literature, the other a partner export — and a
    recommendation that hides which one it rests on is not reviewable.
    """
    if context is None:
        return []
    relations = context.relations[:8]
    if not relations and not context.summary_text:
        return []

    lines = ["", "【图谱依据】"]
    for relation in relations:
        label = relation.relation or relation.evidence
        origin = relation.source_label or relation.source_id
        lines.append(f"· {relation.source} --{label}--> {relation.target}（{origin}）")
    if context.summary_text:
        lines.append("检索摘要：" + context.summary_text.replace("\n", " "))

    # "相关概念", not "候选方向": these are the targets of the top-ranked edges,
    # which the graphs make out of factors and processes rather than techniques.
    concepts = [
        str(item.get("technique")) for item in context.recommendations if item.get("technique")
    ]
    if concepts:
        lines.append("图谱中最相关的概念：" + "、".join(concepts[:5]))
    lines.append("以上关系来自知识图谱检索，供与案例经验相互印证。")
    return lines


def _generate_explanation(scenario: str, state: dict, best_cases: list[dict]) -> str:
    """Generate human-readable textual explanation."""
    scenario_names = {
        "s1_external_input": "外源输入型",
        "s2_internal_release": "内源释放型",
        "s3_algae_bloom": "藻华主导型",
        "s4_chronic_combo": "慢性复合型",
    }
    scenario_triggers = {
        "s1_external_input": ("3日累积降雨", 36, "mm", "rainfall_3d"),
        "s2_internal_release": ("底泥扰动强度", 3, "NTU基线", "turbidity"),
        "s3_algae_bloom": ("叶绿素-a浓度", 8, "μg/L", "chlorophyll_a"),
        "s4_chronic_combo": ("基础浊度持续偏高", 3, "NTU(7天+)", "turbidity"),
    }

    name = scenario_names.get(scenario, scenario)
    trigger = scenario_triggers.get(scenario)

    lines = []

    # Diagnosis reasoning
    lines.append(f'【场景诊断】当前判定为"{name}"场景。')
    if trigger:
        field_name, threshold, unit, key = trigger
        val = state.get(key, "N/A")
        if isinstance(val, (int, float)):
            lines.append(f"依据：{field_name}={val}{unit}，超过阈值{threshold}{unit}，触发该场景识别。")

    turb = state.get("turbidity", 0)
    rain = state.get("rainfall_3d", 0)

    if scenario == "s1_external_input":
        lines.append(f"当前浊度{turb}NTU偏高，结合近3日降雨{rain}mm，判断上游冲刷为主要驱动力。")
        lines.append("建议以加大放水冲刷为核心手段，辅以沉淀池反冲洗加速悬浮物沉降。")
    elif scenario == "s2_internal_release":
        lines.append(f"当前浊度{turb}NTU，降雨量仅{rain}mm，排除外源输入因素。")
        lines.append("推断为底泥翻动释放营养盐及悬浮物，建议精细化流量控制+原位曝气组合方案。")
    elif scenario == "s3_algae_bloom":
        chl = state.get("chlorophyll_a", "N/A")
        lines.append(f"叶绿素-a浓度{chl}μg/L偏高，光照条件充足，藻类繁殖为浊度主导因子。")
        lines.append("建议高强度曝气增氧抑制藻类生长，配合生物制剂加速藻华消退。")
    elif scenario == "s4_chronic_combo":
        lines.append(f"基础浊度{turb}NTU持续偏高，多因素长期叠加，非单一事件驱动。")
        lines.append("建议采用低强度持续性治理方案，配合生态修复措施，逐步改善水质基线。")

    # Case-based reasoning
    if best_cases:
        lines.append("")
        lines.append("【案例支撑】")
        for i, item in enumerate(best_cases):
            c = item["case"]
            sim = item["similarity"]
            sim_pct = int(sim * 100)
            lines.append(
                f"案例{i+1}：{c['title']}（{c['location']}，{c['year']}年），"
                f"相似度{sim_pct}%。"
            )
            lines.append(f"  条件：{c['condition']}。")
            lines.append(f"  措施：{c['summary']}")
            lines.append(f"  效果：浊度削减{c['outcome']['turbidity_reduction_ratio']*100:.0f}%，"
                         f"恢复周期{c['outcome']['recovery_days']}天。")
            lines.append(f"  文献：{c['reference']}")

    # Conclusion
    lines.append("")
    lines.append("【综合建议】")
    if best_cases:
        best = best_cases[0]["case"]
        lines.append(
            f"参考{best['location']}({best['year']}年)相似案例的成功经验，"
            f"该案例在类似工况下取得了{best['outcome']['turbidity_reduction_ratio']*100:.0f}%的浊度削减率。"
        )
    lines.append("本次决策综合考虑当前水质状态、历史案例效果与成本约束，给出上述治理方案。")

    return "\n".join(lines)


@router.post("/explain")
async def generate_explanation(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate case-based explanation for a strategy decision.

    Request body:
        scenario: str - scenario key
        state: dict - water quality state (turbidity, flow_rate, rainfall_3d, etc.)
        knowledge_context: dict - optional graph evidence retrieved by the platform

    Returns:
        explanation: str - textual explanation
        matched_cases: list - top matched cases with similarity scores
        knowledge_context_available: bool - whether graph evidence was used
    """
    scenario = payload.get("scenario", "s1_external_input")
    state = payload.get("state", {})

    # Validated rather than read straight through: this payload is untyped on
    # purpose (the lab page posts it ad hoc), so a malformed context has to be
    # discarded here instead of raising inside the explanation renderer.
    context: KnowledgeContext | None = None
    raw_context = payload.get("knowledge_context")
    if isinstance(raw_context, dict):
        try:
            context = KnowledgeContext.model_validate(raw_context)
        except Exception:  # noqa: BLE001 — a bad context degrades to no context
            context = None

    best_cases = _find_best_cases(scenario, state, top_k=2)
    lines = [_generate_explanation(scenario, state, best_cases)]
    lines.extend(_knowledge_section(context))
    explanation = "\n".join(lines)

    return {
        "scenario": scenario,
        "explanation": explanation,
        "knowledge_context_available": context is not None,
        "matched_cases": [describe(item) for item in best_cases],
    }
