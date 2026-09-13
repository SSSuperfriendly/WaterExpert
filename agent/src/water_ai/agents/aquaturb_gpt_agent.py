from __future__ import annotations

import json
from typing import Any

from ..llm.deepseek_client import DeepSeekClient
from ..visualization.reasoning_viz import ReasoningVisualizer
from .base import BaseAgent


class AquaTurbGPTAgent(BaseAgent):
    def __init__(self, name: str = "AquaTurbGPTAgent", config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.client = DeepSeekClient(config=self.config.get("deepseek", {}))
        self.viz = ReasoningVisualizer()
        
        # Fallback strategies if API fails
        self.fallback_strategies = {
            "s1_external_input": {
                "scenario_confidence": 0.92,
                "objective_weights": {"turbidity_reduction": 0.8, "cost": 0.1, "stability": 0.1},
                "recommended_actions": [{"action": "release_water", "intensity": 0.8}],
            },
            "s2_internal_release": {
                "scenario_confidence": 0.75,
                "objective_weights": {"turbidity_reduction": 0.6, "cost": 0.2, "stability": 0.2},
                "recommended_actions": [{"action": "flow_control", "intensity": 0.5}],
            },
            "s3_algae_bloom": {
                "scenario_confidence": 0.85,
                "objective_weights": {"turbidity_reduction": 0.5, "cost": 0.15, "stability": 0.35},
                "recommended_actions": [{"action": "aeration", "intensity": 0.9}],
            },
            "s4_chronic_combo": {
                "scenario_confidence": 0.70,
                "objective_weights": {"turbidity_reduction": 0.4, "cost": 0.3, "stability": 0.3},
                "recommended_actions": [{"action": "flow_control", "intensity": 0.3}],
            },
        }

    def act(self, planning_input: dict[str, Any]) -> dict[str, Any]:
        """Generate high-level strategy from diagnosis results using DeepSeek.
        
        Args:
            planning_input: Diagnosis results and scenario info
            
        Returns:
            Strategy dict with DeepSeek reasoning and fallback support
        """
        scenario = planning_input.get("scenario", "s2_internal_release")
        diagnosis = planning_input.get("diagnosis", {})
        state = planning_input.get("state") or {}

        # Build prompt for DeepSeek
        prompt = self._build_strategy_prompt(
            scenario,
            diagnosis,
            state=state,
            knowledge_context=planning_input.get("knowledge_context"),
        )
        
        # Get fallback strategy
        fallback = self.fallback_strategies.get(scenario, self.fallback_strategies["s2_internal_release"])
        
        # Call DeepSeek with fallback
        response = self.client.generate_with_fallback(prompt, fallback)
        
        # Parse strategy from response
        strategy = self._parse_strategy_response(response, fallback)
        
        # Generate reasoning visualization if reasoning tokens available
        if response.get("reasoning_tokens"):
            viz_path = self.viz.create_reasoning_viz(
                scenario=scenario,
                reasoning_tokens=response["reasoning_tokens"],
                output_name=f"reasoning_{scenario}.html",
            )
            strategy["reasoning_viz_path"] = viz_path
        
        return {
            "planner": "AquaTurb-GPT",
            "scenario_detected": scenario,
            "strategy": strategy,
            "backend_used": response.get("backend"),
            "model": response.get("model"),
        }

    def _summarize_diagnosis(self, state: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
        """Flatten the nested stage-1 reports into the fields the prompt asks for.

        This is what makes ``primary_drivers`` real. The prompt below has always
        asked for it, and it has always printed ``Unknown`` — not because a key
        was misspelled, but because the coordinator hands over
        ``{"mscim": …, "cmfbe": …, "knowledge_base": …}`` and the prompt read it
        as if it were already flat. The drivers, the confidence and the flow
        condition are all present in that structure; nothing was reading them.
        """
        mscim = diagnosis.get("mscim") or {}
        cmfbe = diagnosis.get("cmfbe") or {}

        drivers = (mscim.get("diagnosis") or {}).get("primary_drivers") or []
        rendered = ", ".join(
            f"{item.get('factor')}({float(item.get('importance', 0.0)):.2f})"
            for item in drivers
            if isinstance(item, dict) and item.get("factor")
        )

        prediction = mscim.get("prediction") or {}
        confidence = prediction.get("turbidity_confidence")
        if confidence is None:
            confidence = (cmfbe.get("predictions") or {}).get("confidence")

        flow_rate = state.get("flow_rate")
        if isinstance(flow_rate, (int, float)):
            if flow_rate < 5:
                flow_condition = f"低（{flow_rate} m³/s）"
            elif flow_rate <= 20:
                flow_condition = f"中（{flow_rate} m³/s）"
            else:
                flow_condition = f"高（{flow_rate} m³/s）"
        else:
            flow_condition = "Unknown"

        net_change = cmfbe.get("net_change")
        return {
            "primary_drivers": rendered or "Unknown",
            "confidence": f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "Unknown",
            "flow_condition": flow_condition,
            "turbidity": state.get("turbidity", "Unknown"),
            "net_change": f"{float(net_change):+.3f}" if isinstance(net_change, (int, float)) else "Unknown",
        }

    def _build_strategy_prompt(
        self,
        scenario: str,
        diagnosis: dict[str, Any],
        state: dict[str, Any] | None = None,
        knowledge_context: dict[str, Any] | None = None,
    ) -> str:
        """Build prompt for DeepSeek strategy generation.

        ``diagnosis`` is accepted in either shape: the coordinator's nested
        ``{"mscim": …, "cmfbe": …}`` reports, which are summarised here, or an
        already-flat summary, which is used as given. Both call conventions work
        rather than one being right and the other silently producing ``Unknown``.
        """
        scenario_descriptions = {
            "s1_external_input": "场景1: 外源输入型 - 降水增加导致通过支流输入大量悬浮物和营养盐",
            "s2_internal_release": "场景2: 内源释放型 - 底泥翻动释放营养盐和悬浮物",
            "s3_algae_bloom": "场景3: 藻华主导型 - 叶绿素-a高且光照充足导致蓝绿藻大量繁殖",
            "s4_chronic_combo": "场景4: 慢性复合型 - 多个因素长期叠加导致基础浊度持续升高",
        }

        summary = (
            self._summarize_diagnosis(state or {}, diagnosis)
            if any(key in diagnosis for key in ("mscim", "cmfbe", "knowledge_base"))
            else diagnosis
        )

        prompt = f"""你是一个水体治理专家，基于诊断结果制定应对策略。

{scenario_descriptions.get(scenario, scenario)}

诊断信息:
- 主要驱动因素: {summary.get('primary_drivers', 'Unknown')}
- 诊断置信度: {summary.get('confidence', 'Unknown')}
- 流量条件: {summary.get('flow_condition', 'Normal')}
- 浊度: {summary.get('turbidity', 'Unknown')} NTU
- 过程净变化: {summary.get('net_change', 'Unknown')}
{self._render_knowledge_section(knowledge_context)}
请生成一个JSON格式的策略，包含以下字段:
{{
    "scenario_confidence": 0-1之间的置信度,
    "objective_weights": {{
        "turbidity_reduction": 成本权重0-1,
        "cost": 成本权重0-1,
        "stability": 稳定性权重0-1
    }},
    "recommended_actions": [
        {{
            "action": "release_water" | "flow_control" | "aeration" | "chemical_dosage",
            "intensity": 0-1之间的强度
        }}
    ],
    "reasoning": "简要说明推理过程"
}}

仅返回JSON，不要其他文本。"""

        return prompt

    def _render_knowledge_section(self, knowledge_context: dict[str, Any] | None) -> str:
        """The literature the platform retrieved, as prompt material.

        This is the step that makes retrieval reach the model at all. Without it
        the graph would be retrieved, cited in the trace, and then ignored by
        the one component whose output anyone reads.

        Edge sources are named because the two graphs are not equals: the
        platform graph is the user's own literature, the inherited one is a
        partner export covering a much wider domain.
        """
        if not isinstance(knowledge_context, dict):
            return ""
        relations = knowledge_context.get("relations") or []
        summary = str(knowledge_context.get("summary_text") or "").strip()
        if not relations and not summary:
            return ""

        lines = ["", "图谱依据（来自知识库检索，引用时请以这些关系为准）:"]
        for relation in relations[:8]:
            if not isinstance(relation, dict):
                continue
            label = relation.get("relation") or relation.get("evidence") or ""
            origin = relation.get("source_label") or relation.get("source_id") or ""
            lines.append(
                f"- {relation.get('source', '')} --{label}--> {relation.get('target', '')}"
                f"（{origin}）"
            )
        if summary:
            lines.append("检索摘要：" + summary.replace("\n", " "))

        # Named "相关概念" rather than "候选方向" deliberately. These are the
        # targets of the top-ranked edges, which on the real graphs are factors
        # and processes — "SEDIMENT RESUSPENSION", "营养盐释放" — not techniques.
        # Offering them as candidate measures would invite the model to
        # recommend resuspending sediment.
        concepts = [
            str(item.get("technique"))
            for item in (knowledge_context.get("recommendations") or [])
            if isinstance(item, dict) and item.get("technique")
        ]
        if concepts:
            lines.append("图谱中最相关的概念：" + "、".join(concepts[:5]))
        lines.append("若图谱依据与诊断结论冲突，请以诊断结论为主并在 reasoning 中说明。")
        return "\n".join(lines) + "\n"

    def _parse_strategy_response(
        self, response: dict[str, Any], fallback: dict[str, Any]
    ) -> dict[str, Any]:
        """Parse strategy from DeepSeek response.
        
        Args:
            response: Response from DeepSeek client
            fallback: Fallback strategy if parsing fails
            
        Returns:
            Parsed strategy dict
        """
        try:
            if response.get("error"):
                return fallback
            
            content = response.get("content", "")
            if not content:
                return fallback
            
            # Try to parse JSON from response
            strategy = json.loads(content)
            
            # Validate required fields
            if all(k in strategy for k in ["scenario_confidence", "objective_weights", "recommended_actions"]):
                return strategy
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        
        return fallback

    def health(self) -> dict[str, Any]:
        return {
            "agent": self.name,
            "backend": self.client.backend_type,
            "status": "ready",
            "fallback_enabled": True,
        }
