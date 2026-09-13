from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import BaseAgent

#: Filled in for graph-derived candidates, which carry evidence rather than a
#: cost model. The keys are not optional: downstream stages index these entries
#: by name, and a graph candidate that omitted them would turn a missing price
#: into a ``KeyError`` several stages later.
DEFAULT_INTENSITY = 0.5
DEFAULT_COST_PER_DAY = 0.0


class KnowledgeBaseAgent(BaseAgent):
    """Candidate techniques for a scenario.

    Two sources, in order. When the platform supplies a ``knowledge_context``,
    its retrieved edges come first, labelled with the graph they came from and
    the citation that makes them checkable. The curated scenario dictionary
    below then follows. Both are always present when both are available: the
    graph knows what the literature says about this water body, and the curated
    dictionary knows what a treatment actually costs to run — dropping either
    would make the recommendation worse in a different way.
    """

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
        curated = list(recommendations.get(scenario, self.knowledge[:top_k]))

        context = query.get("knowledge_context") or {}
        grounded = self._from_context(context, top_k)
        if not grounded:
            return {"source": "KnowledgeBaseAgent", "recommendations": curated[:top_k]}

        return {
            "source": "KnowledgeBaseAgent+GraphRAG",
            "grounded": True,
            "graph_mode": str(context.get("mode") or ""),
            "graph_query": str(context.get("query") or ""),
            "citations": list(context.get("citations") or []),
            "recommendations": grounded + curated,
        }

    def _from_context(self, context: Any, top_k: int) -> list[dict[str, Any]]:
        """Map retrieved edges onto the recommendation shape.

        ``technique`` is the edge's target, which is a factor or a process far
        more often than it is a method — "NUTRIENT RELEASE" is not something
        anyone can schedule. Each entry therefore carries ``origin: "graph"``,
        its ``evidence`` and its ``citation`` alongside, so a consumer can tell a
        literature-derived candidate from a costed technique instead of guessing
        from the name.
        """
        if not isinstance(context, dict):
            return []
        entries = context.get("recommendations") or context.get("relations") or []
        if not isinstance(entries, list):
            return []

        out: list[dict[str, Any]] = []
        for entry in entries[:max(0, top_k)]:
            if not isinstance(entry, dict):
                continue
            technique = str(entry.get("technique") or entry.get("target") or "").strip()
            if not technique:
                continue
            out.append(
                {
                    "technique": technique,
                    "intensity": DEFAULT_INTENSITY,
                    "cost_per_day": DEFAULT_COST_PER_DAY,
                    "origin": "graph",
                    "relation": str(entry.get("relation") or ""),
                    "evidence": str(entry.get("evidence") or ""),
                    "source_id": str(entry.get("source_id") or ""),
                    "citation": next(
                        (
                            str(citation.get("marker", ""))
                            for citation in (context.get("citations") or [])
                            if isinstance(citation, dict)
                            and citation.get("kind") == "relation"
                            and citation.get("target") == technique
                            and citation.get("relation", "") == str(entry.get("relation") or "")
                        ),
                        "",
                    ),
                }
            )
        return out

    def health(self) -> dict[str, Any]:
        return {"agent": self.name, "seed_size": len(self.knowledge), "status": "ready"}
