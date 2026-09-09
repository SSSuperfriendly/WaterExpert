from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import BaseAgent


class KnowledgeBaseAgent(BaseAgent):
    def __init__(self, name: str = "KnowledgeBaseAgent", config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.seed_path = Path(self.config.get("seed_data_path", "data/tech_knowledge_base/tech_quadruples.jsonl"))
        self.knowledge = self._load_seed_data()

    def _load_seed_data(self) -> list[dict[str, Any]]:
        if not self.seed_path.exists():
            return []
        items: list[dict[str, Any]] = []
        with self.seed_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return items

    def act(self, query: dict[str, Any]) -> dict[str, Any]:
        """Retrieve candidate techniques matching current scenario."""
        top_k = int(self.config.get("top_k", 3))
        
        recommendations = {
            "s1_external_input": [
                {"technique": "加大放水冲刷", "intensity": 0.8, "cost_per_day": 15.0},
                {"technique": "增加沉淀池反冲", "intensity": 0.6, "cost_per_day": 8.0},
            ],
            "s2_internal_release": [
                {"technique": "精细化流量控制", "intensity": 0.5, "cost_per_day": 6.0},
                {"technique": "原位曝气", "intensity": 0.7, "cost_per_day": 10.0},
            ],
            "s3_algae_bloom": [
                {"technique": "增氧曝气", "intensity": 0.8, "cost_per_day": 12.0},
                {"technique": "生物制剂投加", "intensity": 0.6, "cost_per_day": 20.0},
            ],
            "s4_chronic_combo": [
                {"technique": "低强度调理", "intensity": 0.3, "cost_per_day": 4.0},
                {"technique": "长期曝气", "intensity": 0.4, "cost_per_day": 8.0},
            ],
        }
        
        scenario = query.get("scenario_type", "s2_internal_release")
        candidates = recommendations.get(scenario, self.knowledge[:top_k])
        return {"source": "KnowledgeBaseAgent", "recommendations": candidates[:top_k]}

    def health(self) -> dict[str, Any]:
        return {"agent": self.name, "seed_size": len(self.knowledge), "status": "ready"}
