"""The materials block, its citation index, and the deterministic fallback.

This is the layer where a mistake is invisible rather than loud. The materials
text is what the model is told, and the citation index is what the reader is
shown; both are assembled from the same loop, so a variable reused for two
different facts corrupts the prompt *and* the API at once while every test that
only checks "is there an answer" still passes.

Two such mistakes lived here:

* ``label`` held the source's display name and was then reassigned to the words
  "证据"/"关系描述" before either the ``来源:`` line or ``citations[].source_label``
  read it. Every relation was attributed to a graph called 关系描述.
* The fallback chain renderer bracketed its edge labels — ``[导致]``, ``[相关]``
  — which is the shape of a citation marker while resolving as neither a
  backend ``MARKER_RE`` nor a frontend ``CITATION_RE``. Text that looks
  clickable and is not.
"""

from __future__ import annotations

import unittest

from backend.app.services.graph_rag.answering import (
    MARKER_RE,
    build_materials,
    fallback_answer,
    source_of,
)
from backend.app.services.graph_rag.index import Relation, node_key
from backend.app.services.graph_rag.local_search import PathCandidate


class _Source:
    def __init__(self, label: str) -> None:
        self.label = label


class _Bundle:
    """Just enough bundle for ``build_materials`` to label a relation."""

    def __init__(self, labels: dict[str, str]) -> None:
        self.sources = {source_id: _Source(label) for source_id, label in labels.items()}


def _relation(
    source: str = "风",
    target: str = "浊度",
    *,
    source_id: str = "platform",
    relation: str = "导致",
    evidence: str = "风浪扰动底泥",
    source_file: str = "clean_a (4).txt",
) -> Relation:
    return Relation(
        source=node_key(source_id, source),
        target=node_key(source_id, target),
        relation=relation,
        evidence=evidence,
        source_file=source_file,
    )


class SourceIdTest(unittest.TestCase):
    def test_source_id_comes_from_the_namespace(self) -> None:
        relation = _relation(source_id="inherited")
        self.assertEqual(relation.source_id, "inherited")
        self.assertEqual(source_of(relation), "inherited")

    def test_as_dict_carries_source_id_without_touching_the_old_keys(self) -> None:
        payload = _relation(source_id="inherited").as_dict()
        self.assertEqual(payload["source_id"], "inherited")
        # The four keys the UI has always read keep their names and their
        # prefix-stripped values: this addition must be additive or every
        # existing consumer breaks.
        self.assertEqual(payload["source"], "风")
        self.assertEqual(payload["target"], "浊度")
        self.assertEqual(payload["relation"], "导致")
        self.assertEqual(payload["evidence"], "风浪扰动底泥")
        self.assertNotIn("::", payload["source"])
        self.assertNotIn("::", payload["target"])


class MaterialsLabelTest(unittest.TestCase):
    def test_the_source_line_names_the_graph_not_the_evidence_kind(self) -> None:
        bundle = _Bundle({"platform": "基线图谱", "inherited": "继承图谱（合作方 GraphRAG）"})
        materials, citations, _numbers = build_materials(
            bundle, [], [_relation(source_id="inherited")], [], []
        )
        self.assertIn("来源: clean_a (4).txt（继承图谱（合作方 GraphRAG））", materials)
        self.assertNotIn("（关系描述）", materials)

    def test_the_evidence_kind_still_labels_the_evidence_line(self) -> None:
        bundle = _Bundle({"platform": "基线图谱"})
        labelled = _relation(relation="导致")
        unlabelled = _relation(relation="", evidence="描述本身即关系")
        materials, _citations, _numbers = build_materials(
            bundle, [], [labelled, unlabelled], [], []
        )
        self.assertIn("证据: 风浪扰动底泥", materials)
        self.assertIn("关系描述: 描述本身即关系", materials)

    def test_citation_source_label_is_the_graph(self) -> None:
        bundle = _Bundle({"platform": "基线图谱", "inherited": "继承图谱（合作方 GraphRAG）"})
        _materials, citations, _numbers = build_materials(
            bundle,
            [],
            [_relation(source_id="inherited"), _relation(source_id="platform")],
            [],
            [],
        )
        self.assertEqual(
            [citation["source_label"] for citation in citations],
            ["继承图谱（合作方 GraphRAG）", "基线图谱"],
        )
        self.assertEqual(
            [citation["source_id"] for citation in citations], ["inherited", "platform"]
        )

    def test_an_unknown_source_falls_back_to_its_id(self) -> None:
        _materials, citations, _numbers = build_materials(
            _Bundle({}), [], [_relation(source_id="ghost")], [], []
        )
        self.assertEqual(citations[0]["source_label"], "ghost")


class FallbackMarkerTest(unittest.TestCase):
    """The fallback is what runs with no API key — the default in production."""

    def _path(self, relation: Relation) -> PathCandidate:
        return PathCandidate(
            source_id=relation.source_id,
            nodes=[relation.source, relation.target],
            edges=[relation],
        )

    def test_edge_labels_are_not_shaped_like_citations(self) -> None:
        relation = _relation(relation="导致")
        answer = fallback_answer([self._path(relation)], [relation], [], [])
        self.assertNotIn("[导致]", answer)
        self.assertIn("--导致-->", answer)

    def test_an_unlabelled_edge_does_not_invent_a_marker_either(self) -> None:
        """Every inherited edge is unlabelled; it used to render as ``[相关]``."""
        relation = _relation(source_id="inherited", relation="", evidence="沉积物再悬浮")
        answer = fallback_answer([self._path(relation)], [relation], [], [])
        self.assertNotIn("[相关]", answer)

    def test_the_real_markers_are_still_emitted(self) -> None:
        """The fix must not have removed the citations along with the fakes."""
        relation = _relation()
        answer = fallback_answer([self._path(relation)], [relation], [], [])
        self.assertIn("[关系1]", answer)
        # The chain line is annotated with the markers of its own edges, so a
        # well-organised answer is not reported as half-unsupported.
        chain_line = next(line for line in answer.splitlines() if line.startswith("- "))
        self.assertIn("[关系1]", chain_line)

    def test_every_bracketed_token_resolves_as_a_marker(self) -> None:
        """The property, not the instances: no ``[...]`` that is not a marker.

        A bracketed token the backend cannot resolve is text the reader will
        still try to click. Checking the whole rendered answer, rather than the
        two labels that happened to be wrong, is what makes this hold for the
        next label someone adds.
        """
        relations = [_relation(), _relation(relation="", source_id="inherited")]
        answer = fallback_answer(
            [self._path(relation) for relation in relations], relations, [], []
        )
        bracketed = {
            token
            for token in answer.replace("[", " [").split()
            if token.startswith("[") and token.endswith("]")
        }
        self.assertTrue(bracketed)
        for token in bracketed:
            self.assertTrue(MARKER_RE.fullmatch(token), f"{token} looks like a citation")


if __name__ == "__main__":
    unittest.main()
