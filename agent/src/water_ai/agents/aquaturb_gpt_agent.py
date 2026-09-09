from __future__ import annotations

import json
from typing import Any

from .base import BaseAgent
from ..llm.deepseek_client import DeepSeekClient
from ..visualization.reasoning_viz import ReasoningVisualizer


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
        
        # Build prompt for DeepSeek
        prompt = self._build_strategy_prompt(scenario, diagnosis)
        
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

    def _build_strategy_prompt(self, scenario: str, diagnosis: dict[str, Any]) -> str:
        """Build prompt for DeepSeek strategy generation.
        
        Args:
            scenario: Scenario key
            diagnosis: Diagnosis results from agents
            
        Returns:
            Formatted prompt string
        """
        scenario_descriptions = {
            "s1_external_input": "场景1: 外源输入型 - 降水增加导致通过支流输入大量悬浮物和营养盐",
            "s2_internal_release": "场景2: 内源释放型 - 底泥翻动释放营养盐和悬浮物",
            "s3_algae_bloom": "场景3: 藻华主导型 - 叶绿素-a高且光照充足导致蓝绿藻大量繁殖",
            "s4_chronic_combo": "场景4: 慢性复合型 - 多个因素长期叠加导致基础浊度持续升高",
        }
        
        prompt = f"""你是一个水体治理专家，基于诊断结果制定应对策略。

{scenario_descriptions.get(scenario, scenario)}

诊断信息:
- 主要驱动因素: {diagnosis.get('primary_drivers', 'Unknown')}
- 诊断置信度: {diagnosis.get('confidence', 'Unknown')}
- 流量条件: {diagnosis.get('flow_condition', 'Normal')}
- 浊度: {diagnosis.get('turbidity', 'Unknown')} NTU

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
