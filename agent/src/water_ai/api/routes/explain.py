"""Explanation generation route - provides case-based reasoning and textual analysis."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["explain"])

CASE_LIBRARY_PATH = Path(__file__).resolve().parents[4] / "data" / "case_library" / "cases.json"


def _load_cases() -> list[dict[str, Any]]:
    if not CASE_LIBRARY_PATH.exists():
        return []
    with CASE_LIBRARY_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _similarity(case_cond: dict, input_state: dict) -> float:
    """Compute simple normalized distance-based similarity."""
    keys = ["rainfall_3d", "turbidity", "flow_rate"]
    dist = 0.0
    count = 0
    for k in keys:
        cv = case_cond.get(k)
        iv = input_state.get(k)
        if cv is not None and iv is not None:
            scale = max(abs(cv), abs(iv), 1.0)
            dist += ((cv - iv) / scale) ** 2
            count += 1
    if count == 0:
        return 0.0
    return max(0.0, 1.0 - math.sqrt(dist / count))


def _find_best_cases(scenario: str, state: dict, top_k: int = 2) -> list[dict[str, Any]]:
    cases = _load_cases()
    matched = [c for c in cases if c["scenario"] == scenario]
    if not matched:
        matched = cases
    scored = [(c, _similarity(c.get("condition", {}), state)) for c in matched]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [{"case": c, "similarity": round(s, 3)} for c, s in scored[:top_k]]


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
    flow = state.get("flow_rate", 0)
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

    Returns:
        explanation: str - textual explanation
        matched_cases: list - top matched cases with similarity scores
    """
    scenario = payload.get("scenario", "s1_external_input")
    state = payload.get("state", {})

    best_cases = _find_best_cases(scenario, state, top_k=2)
    explanation = _generate_explanation(scenario, state, best_cases)

    return {
        "scenario": scenario,
        "explanation": explanation,
        "matched_cases": [
            {
                "id": item["case"]["id"],
                "title": item["case"]["title"],
                "location": item["case"]["location"],
                "year": item["case"]["year"],
                "similarity": item["similarity"],
                "summary": item["case"]["summary"],
                "reference": item["case"]["reference"],
                "outcome": item["case"]["outcome"],
            }
            for item in best_cases
        ],
    }
