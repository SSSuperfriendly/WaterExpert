from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..data import case_library
from .base import BaseAgent

#: How many cases ride along as evidence for the scenario's recommendations.
CASE_EVIDENCE_CASES = 2

#: The scenario key assumed when the router could not classify the state.
FALLBACK_SCENARIO = "s2_internal_release"

#: The scenario vocabulary, and which field of a case's ``intervention`` each
#: technique corresponds to.
#:
#: This table is a statement about the platform's own technique names, not a
#: derivation from the data: ``原位曝气`` *is* aeration, the case library records
#: aeration as ``aeration_intensity``, so the case's kilowatts are that
#: technique's intensity. It is written out rather than inferred because a
#: name-matching heuristic that put a case's dosing rate behind 增加沉淀池反冲
#: would be indistinguishable, to a reader, from a real reading.
#:
#: ``None`` means the library records nothing for that technique. The technique
#: is still offered — it is a real option an operator can take — but it is
#: offered without a number, which is the honest form of "no case supports this".
SCENARIO_TECHNIQUES: dict[str, tuple[tuple[str, str | None], ...]] = {
    "s1_external_input": (
        ("加大放水冲刷", "release_rate"),
        ("增加沉淀池反冲", None),
    ),
    "s2_internal_release": (
        ("精细化流量控制", "release_rate"),
        ("原位曝气", "aeration_intensity"),
    ),
    "s3_algae_bloom": (
        ("增氧曝气", "aeration_intensity"),
        ("生物制剂投加", "chemical_dosage"),
    ),
    "s4_chronic_combo": (
        ("低强度调理", "aeration_intensity"),
        ("长期曝气", "aeration_intensity"),
    ),
}


class KnowledgeBaseAgent(BaseAgent):
    """Candidate techniques for a scenario, each one priced by what it rests on.

    Three sources, in order. When the platform supplies a ``knowledge_context``,
    its retrieved edges come first, labelled with the graph they came from and
    the citation that makes them checkable. The scenario's own technique
    vocabulary then follows, and each of its numbers is read off the case
    library — the closest documented intervention for a water body in a
    comparable condition, carried with the case id and the paper it was
    published in. The technology quadruples are the last resort, for a scenario
    no vocabulary covers.

    Only the middle source has numbers at all. A literature edge records that
    one thing influences another, and no graph carries a cost model; an edge
    that arrived with an intensity attached would be showing the reader a
    fabricated measurement. Those entries therefore say ``None`` — and the cost
    dimension is not lost, because the cases do report it, as a cost *saving*
    against the conventional treatment, cited by case id.
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

        scenario = str(query.get("scenario_type") or FALLBACK_SCENARIO)
        state = {
            key: value
            for key, value in query.items()
            if key not in ("scenario_type", "knowledge_context")
        }

        # ``fallback_to_all=False`` is what keeps a case from another scenario
        # from lending this one its dosing rate. A scenario the library does not
        # document gets no cases, and therefore no numbers — not somebody
        # else's numbers.
        cases = case_library.cases_for(
            scenario, state, top_k=CASE_EVIDENCE_CASES, fallback_to_all=False
        )
        curated = self._from_scenario(scenario, cases) or self._from_seed(top_k)

        context = query.get("knowledge_context") or {}
        grounded = self._from_context(context, top_k)
        evidence = [case_library.describe(item) for item in cases]

        if not grounded:
            return {
                "source": "KnowledgeBaseAgent",
                "recommendations": curated[:top_k],
                "case_evidence": evidence,
            }

        return {
            "source": "KnowledgeBaseAgent+GraphRAG",
            "grounded": True,
            "graph_mode": str(context.get("mode") or ""),
            "graph_query": str(context.get("query") or ""),
            "citations": list(context.get("citations") or []),
            "recommendations": grounded + curated,
            "case_evidence": evidence,
        }

    @staticmethod
    def _entry(technique: str, origin: str) -> dict[str, Any]:
        """The shape every candidate carries, whatever it rests on.

        Built in one place so the union stays uniform and a consumer iterating
        ``recommendations`` never has to branch on ``origin`` to find out
        whether a key is present. ``None`` is the honest value for a parameter
        no source recorded; the alternative, an omitted key, would turn "the
        dose is unknown" into a ``KeyError`` several stages later.
        """
        return {
            "technique": technique,
            "origin": origin,
            "intensity": None,
            "intensity_unit": None,
            "intensity_field": None,
            "cost_per_day": None,
            "case_id": None,
            "case_similarity": None,
            "reference": "",
            # Empty for a technique that rests on a case rather than on a graph;
            # graph-only keys such as ``evidence`` stay graph-only, because
            # there the meaning differs by origin and a reader has to branch.
            "source_label": "",
        }

    def _from_scenario(
        self, scenario: str, cases: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """The scenario's techniques, priced by the closest case that recorded them.

        The case is the one most similar to the *current* state among this
        scenario's cases, so 加大放水冲刷 is quoted at the flow rate a comparable
        water body was actually flushed at — not at an average of all eight, and
        not at a normalised score with no unit.
        """
        techniques = SCENARIO_TECHNIQUES.get(scenario)
        if not techniques:
            return []

        best = cases[0] if cases else {}
        case = best.get("case") or {}
        case_id = str(case.get("id") or "")
        similarity = best.get("similarity")

        out: list[dict[str, Any]] = []
        for technique, field in techniques:
            entry = self._entry(technique, "scenario")
            measured = case_library.reading(case, field) if field else None
            if measured is not None and case_id:
                entry.update(
                    intensity=measured["value"],
                    intensity_unit=measured["unit"],
                    intensity_field=measured["field"],
                    case_id=case_id,
                    case_similarity=similarity,
                    reference=str(case.get("reference") or ""),
                )
            out.append(entry)
        return out

    def _from_seed(self, top_k: int) -> list[dict[str, Any]]:
        """The technology quadruples, for a scenario the vocabulary does not cover.

        The seed rows name a ``technology`` rather than a ``technique``, so the
        key is translated here. Without the translation the entry reached the
        report with no technique name at all, and every consumer that looks
        entries up by that name — the concept list in the planning prompt among
        them — silently rendered nothing.
        """
        out: list[dict[str, Any]] = []
        for item in self.knowledge[: max(0, top_k)]:
            technology = str(item.get("technology") or "").strip()
            if not technology:
                continue
            entry = self._entry(technology, "seed")
            entry["environment"] = str(item.get("environment") or "")
            entry["effect"] = str(item.get("effect") or "")
            out.append(entry)
        return out

    def _from_context(self, context: Any, top_k: int) -> list[dict[str, Any]]:
        """Map retrieved edges onto the recommendation shape.

        ``technique`` is the edge's target, which is a factor or a process far
        more often than it is a method — "NUTRIENT RELEASE" is not something
        anyone can schedule. Each entry therefore carries ``origin: "graph"``,
        its ``evidence`` and its ``citation`` alongside, so a consumer can tell a
        literature-derived candidate from a costed technique instead of guessing
        from the name.

        The parameters are ``None``, and that is the point rather than an
        omission. An edge records that X influences Y; it does not record how
        much of anything to dose, and neither graph carries a cost model. The
        defaults this used to fill in — an intensity of 0.5 and a price of zero —
        rendered in the report exactly like measured values, so wherever the
        evidence stopped the reader was shown an invented number instead. A
        ``None`` says the evidence stops here.
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
            recommendation = self._entry(technique, "graph")
            recommendation.update(
                relation=str(entry.get("relation") or ""),
                evidence=str(entry.get("evidence") or ""),
                source_id=str(entry.get("source_id") or ""),
                # The graph's own name for itself, so a plan can say 基线图谱
                # rather than leaving the reader to decode "platform". Absent
                # from a platform that predates the field, and then empty.
                source_label=str(entry.get("source_label") or ""),
                citation=next(
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
            )
            out.append(recommendation)
        return out

    def health(self) -> dict[str, Any]:
        return {"agent": self.name, "seed_size": len(self.knowledge), "status": "ready"}
