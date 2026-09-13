"""The subgraph the canvas draws — and the crash that made it necessary.

The view panel used to be handed the whole platform graph plus a list of node
ids to brighten. That is only coherent while the ids and the drawn nodes come
from the same graph, and retrieval runs over two: an answer grounded in the
inherited graph asked the canvas to focus 18k English entities it had never
drawn, and ``network.fit`` threw on the first unknown id — with no error
boundary above it, that is a blank "This page couldn't load" page.

So the assertions here are mostly about *coherence* rather than about ranking:
that both sources can be drawn at all, that an id means one thing, that no edge
is ever emitted without its endpoints, and that what could not be found is
reported instead of dropped. Each of those is a property whose absence is a
crash or a silent lie rather than a worse answer.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.app.services.graph_rag import subgraph as subgraph_module
from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.global_search import attach_source_communities
from backend.app.services.graph_rag.index import load_index, node_key
from backend.app.services.graph_rag.sources import (
    INHERITED_SOURCE_ID,
    PLATFORM_SOURCE_ID,
    load_inherited_source,
    load_platform_source,
)
from backend.app.services.kg_service import save_kg


def _platform_relations() -> list[dict]:
    return [
        {
            "source": "风",
            "source_type": "环境因子",
            "relation": "导致",
            "target": "浊度",
            "target_type": "清澈度指标",
            "evidence": "风浪扰动底泥，浊度上升",
            "source_file": "clean_a (4).txt",
        },
        {
            # A parallel edge: same ordered pair, different relation. Two rows
            # that collapse into one DataSet entry are two citations the user
            # can never tell apart.
            "source": "风",
            "source_type": "环境因子",
            "relation": "影响",
            "target": "浊度",
            "target_type": "清澈度指标",
            "evidence": "风速与浊度呈正相关",
            "source_file": "clean_a (4).txt",
        },
        {
            "source": "悬浮物",
            "source_type": "水质因子",
            "relation": "影响",
            "target": "浊度",
            "target_type": "清澈度指标",
            "evidence": "悬浮物散射光线",
            "source_file": "clean_a (4).txt",
        },
        {
            # Reaches outside the three entities a question usually cites, so
            # "expand one hop" has something to expand into.
            "source": "降雨",
            "source_type": "环境因子",
            "relation": "影响",
            "target": "风",
            "target_type": "环境因子",
            "evidence": "降雨伴随风场变化",
            "source_file": "clean_a (4).txt",
        },
    ]


def _inherited_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source": "AGRICULTURE",
                "target": "SEDIMENT",
                "weight": 2.0,
                "description": "农业活动是土壤侵蚀和沉积物负荷增加的主要原因",
                "text_unit_ids": "[]",
                "id": "r1",
                "human_readable_id": 1,
                "source_degree": 40,
                "target_degree": 55,
                "rank": 1,
            },
            {
                "source": "SEDIMENT",
                "target": "TURBIDITY",
                "weight": 1.5,
                "description": "沉积物再悬浮导致水体浊度升高",
                "text_unit_ids": "[]",
                "id": "r2",
                "human_readable_id": 2,
                "source_degree": 55,
                "target_degree": 593,
                "rank": 2,
            },
        ]
    )


def _bundle(tmp: Path, *, communities: bool = False):
    """A two-source index built from synthetic data — no real parquet."""
    kg_dir = tmp / "kg"
    save_kg([dict(row) for row in _platform_relations()], kg_dir)

    parquet = tmp / "create_final_relationships.parquet"
    _inherited_frame().to_parquet(parquet, index=False)

    sources = [
        load_platform_source(kg_dir, None),
        load_inherited_source(parquet),
    ]
    bundle = load_index([source for source in sources if source is not None])

    if communities:
        config = GraphRagConfig()
        for source in bundle.sources.values():
            attach_source_communities(source, config, content_hash_value="test")
    return bundle


def _ids(payload: dict) -> set[str]:
    return {node["id"] for node in payload["nodes"]}


class BothSourcesAreDrawableTest(unittest.TestCase):
    """The regression: the inherited graph was never drawable at all."""

    def test_an_inherited_entity_comes_back_as_a_node(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[
                    {"source_id": INHERITED_SOURCE_ID, "name": "AGRICULTURE"},
                    {"source_id": INHERITED_SOURCE_ID, "name": "SEDIMENT"},
                ],
            )

            self.assertIn(node_key(INHERITED_SOURCE_ID, "AGRICULTURE"), _ids(payload))
            self.assertTrue(payload["edges"])
            self.assertEqual(payload["missing"], [])

    def test_the_two_sources_can_be_drawn_together(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[
                    {"source_id": PLATFORM_SOURCE_ID, "name": "风"},
                    {"source_id": PLATFORM_SOURCE_ID, "name": "浊度"},
                    {"source_id": INHERITED_SOURCE_ID, "name": "SEDIMENT"},
                    {"source_id": INHERITED_SOURCE_ID, "name": "TURBIDITY"},
                ],
            )

            self.assertEqual(
                {source["source_id"] for source in payload["sources"]},
                {PLATFORM_SOURCE_ID, INHERITED_SOURCE_ID},
            )

    def test_the_same_name_in_both_graphs_stays_two_nodes(self) -> None:
        """``SEDIMENT`` and a platform entity of the same name must not merge."""
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[
                    {"source_id": PLATFORM_SOURCE_ID, "name": "沉积物"},
                    {"source_id": INHERITED_SOURCE_ID, "name": "沉积物"},
                ],
            )
            ids = _ids(payload)
            self.assertNotEqual(ids, {node_key(PLATFORM_SOURCE_ID, "沉积物")})


class IdentityTest(unittest.TestCase):
    def test_a_node_id_is_the_namespaced_key(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle, nodes=[{"source_id": PLATFORM_SOURCE_ID, "name": "风"}]
            )
            node = next(n for n in payload["nodes"] if n["name"] == "风")
            self.assertEqual(node["id"], "platform::风")
            self.assertEqual(node["source_id"], PLATFORM_SOURCE_ID)

    def test_a_namespaced_id_round_trips(self) -> None:
        """What the API returns can be sent straight back as a request."""
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            first = subgraph_module.subgraph(
                bundle, nodes=[{"source_id": INHERITED_SOURCE_ID, "name": "SEDIMENT"}]
            )
            sent_back = subgraph_module.subgraph(
                bundle, nodes=[node["id"] for node in first["nodes"]]
            )
            self.assertEqual(_ids(first), _ids(sent_back))
            self.assertEqual(sent_back["missing"], [])

    def test_a_bare_name_is_refused_rather_than_guessed(self) -> None:
        """A name alone is ambiguous across two graphs — guessing is the bug."""
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(bundle, nodes=["TURBIDITY"])
            self.assertEqual(payload["nodes"], [])
            self.assertEqual(payload["edges"], [])

    def test_an_unknown_entity_is_reported_not_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[
                    {"source_id": PLATFORM_SOURCE_ID, "name": "不存在的实体"},
                    {"source_id": INHERITED_SOURCE_ID, "name": "风"},
                ],
            )
            self.assertEqual(
                payload["missing"],
                [
                    {"source_id": PLATFORM_SOURCE_ID, "name": "不存在的实体"},
                    {"source_id": INHERITED_SOURCE_ID, "name": "风"},
                ],
            )


class IntegrityTest(unittest.TestCase):
    """vis-network raises on an edge whose endpoint is not in the same DataSet."""

    def assert_no_dangling(self, payload: dict) -> None:
        ids = _ids(payload)
        for edge in payload["edges"]:
            self.assertIn(edge["source"], ids, edge["id"])
            self.assertIn(edge["target"], ids, edge["id"])

    def test_every_edge_endpoint_is_drawn(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[{"source_id": PLATFORM_SOURCE_ID, "name": "风"}],
                include_neighbours=True,
            )
            self.assert_no_dangling(payload)

    def test_a_cap_bounds_the_expansion_not_the_cited_set(self) -> None:
        """The cap is spent on the surroundings, never on the answer's evidence.

        A cited entity that the cap dropped would leave a citation pointing at
        nothing, so the cited set is kept whatever ``max_nodes`` says — the cap
        governs what the *expansion* may add.
        """
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            cited = ["风", "浊度", "悬浮物"]
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[
                    {"source_id": PLATFORM_SOURCE_ID, "name": name} for name in cited
                ],
                include_neighbours=True,
                max_nodes=3,
            )
            self.assert_no_dangling(payload)
            self.assertEqual(
                _ids(payload),
                {node_key(PLATFORM_SOURCE_ID, name) for name in cited},
            )
            self.assertTrue(payload["truncated"])

    def test_edge_ids_are_unique_even_between_parallel_edges(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[
                    {"source_id": PLATFORM_SOURCE_ID, "name": "风"},
                    {"source_id": PLATFORM_SOURCE_ID, "name": "浊度"},
                ],
            )
            ids = [edge["id"] for edge in payload["edges"]]
            self.assertEqual(len(ids), len(set(ids)))
            # Both relations between 风 and 浊度 survived. One DataSet id for
            # both would have merged them and silently eaten a citation.
            self.assertEqual(len(ids), 2)


class CitedEdgesSurviveTest(unittest.TestCase):
    """Whatever else a request asks for, the cited edges are drawn."""

    def test_a_cap_never_drops_a_cited_edge_for_an_uncited_one(self) -> None:
        """The invariant is ordering, not survival: the cap can drop *something*.

        What it must never do is drop an edge the answer cited while keeping one
        it merely reached. Sorted by id alone, a boundary edge can sort ahead of
        a cited one and take its slot — which is a citation quietly missing from
        the picture that claims to justify the answer.
        """
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[
                    {"source_id": PLATFORM_SOURCE_ID, "name": name}
                    for name in ("风", "浊度")
                ],
                include_neighbours=True,
                max_edges=2,
            )
            drawn = [(edge["source"], edge["target"]) for edge in payload["edges"]]
            # Both cited relations between 风 and 浊度, and nothing else: the
            # uncited 悬浮物 -> 浊度 edge that the expansion reached is left out.
            self.assertEqual(
                drawn,
                [
                    (node_key(PLATFORM_SOURCE_ID, "风"), node_key(PLATFORM_SOURCE_ID, "浊度")),
                    (node_key(PLATFORM_SOURCE_ID, "风"), node_key(PLATFORM_SOURCE_ID, "浊度")),
                ],
            )
            self.assertTrue(payload["truncated"])

    def test_only_cited_edges_are_drawn_by_default(self) -> None:
        """Edges one hop outside the retrieval are not what the answer used."""
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[
                    {"source_id": PLATFORM_SOURCE_ID, "name": "风"},
                    {"source_id": PLATFORM_SOURCE_ID, "name": "浊度"},
                ],
            )
            drawn = {(edge["source"], edge["target"]) for edge in payload["edges"]}
            self.assertNotIn(
                (node_key(PLATFORM_SOURCE_ID, "悬浮物"), node_key(PLATFORM_SOURCE_ID, "浊度")),
                drawn,
            )
            self.assertNotIn(node_key(PLATFORM_SOURCE_ID, "悬浮物"), _ids(payload))


class CommunityExpansionTest(unittest.TestCase):
    def test_a_community_contributes_its_members(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw), communities=True)
            community = next(
                community
                for source in bundle.sources.values()
                for community in (source.communities or [])
            )
            payload = subgraph_module.subgraph(
                bundle, community_ids=[community["community_id"]]
            )
            self.assertTrue(payload["nodes"])
            self.assertEqual(payload["unresolved_communities"], [])

    def test_an_unknown_community_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw), communities=True)
            payload = subgraph_module.subgraph(bundle, community_ids=["nope:c9999"])
            self.assertEqual(payload["unresolved_communities"], ["nope:c9999"])
            self.assertEqual(payload["nodes"], [])


class FocusTest(unittest.TestCase):
    def test_focus_resolves_to_a_drawn_edge_id(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[
                    {"source_id": PLATFORM_SOURCE_ID, "name": "风"},
                    {"source_id": PLATFORM_SOURCE_ID, "name": "浊度"},
                ],
                focus={
                    "source_id": PLATFORM_SOURCE_ID,
                    "source": "风",
                    "target": "浊度",
                    "index": 1,
                },
            )
            drawn = {edge["id"] for edge in payload["edges"]}
            self.assertIn(payload["focus_edge_id"], drawn)
            self.assertNotEqual(payload["focus_edge_id"], payload["edges"][0]["id"])

    def test_focus_on_an_edge_that_was_not_drawn_is_null(self) -> None:
        """An id the canvas was never given is not something to highlight."""
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle,
                nodes=[{"source_id": PLATFORM_SOURCE_ID, "name": "风"}],
                focus={
                    "source_id": INHERITED_SOURCE_ID,
                    "source": "AGRICULTURE",
                    "target": "SEDIMENT",
                    "index": 0,
                },
            )
            self.assertIsNone(payload["focus_edge_id"])

    def test_focus_tolerates_a_malformed_payload(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            for focus in (None, {}, "风", {"source_id": PLATFORM_SOURCE_ID}):
                payload = subgraph_module.subgraph(
                    bundle,
                    nodes=[{"source_id": PLATFORM_SOURCE_ID, "name": "风"}],
                    focus=focus,
                )
                self.assertIsNone(payload["focus_edge_id"])


class EmptyRequestTest(unittest.TestCase):
    def test_nothing_known_is_an_empty_payload_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(bundle)
            self.assertEqual(payload["nodes"], [])
            self.assertEqual(payload["edges"], [])
            self.assertEqual(payload["sources"], [])
            self.assertIsNone(payload["focus_edge_id"])
            self.assertFalse(payload["truncated"])

    def test_sources_describe_only_what_was_drawn(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = _bundle(Path(raw))
            payload = subgraph_module.subgraph(
                bundle, nodes=[{"source_id": PLATFORM_SOURCE_ID, "name": "风"}]
            )
            self.assertEqual(
                [source["source_id"] for source in payload["sources"]],
                [PLATFORM_SOURCE_ID],
            )
            self.assertEqual(payload["sources"][0]["label_key"], "kg.source.runtime")


if __name__ == "__main__":
    unittest.main()
