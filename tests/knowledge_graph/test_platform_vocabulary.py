"""The bridge between the platform's field registry and the graph's names.

What is being tested is a *refusal* as much as a match. The bridge exists
because ``平均气温`` and ``AIR TEMPERATURE`` are one quantity under two
vocabularies and no code path connected them; it must close that gap without
becoming a licence to seed a traversal from any entity that happens to share a
word. Both halves are asserted here: the gaps it closes, and the near-misses it
declines.

No real graph is needed for the vocabulary tests — the alignment is a pure
function of two strings. The one test that does need a graph builds a
two-entity inherited parquet in a temp directory, which is the same approach
``test_graph_rag_index`` takes for the same reason: the 18 MB production parquet
must not be a prerequisite for a unit test.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.entity_link import EntityLexicon
from backend.app.services.graph_rag.index import IndexBundle, load_index
from backend.app.services.graph_rag.platform_vocabulary import (
    MAX_ENTITIES_PER_TERM,
    PlatformVocabulary,
    platform_terms,
    vocabulary,
)
from backend.app.services.graph_rag.sources import load_inherited_source


def terms_by_canonical() -> dict[str, object]:
    return {term.canonical: term for term in platform_terms()}


class RegistryCoverageTest(unittest.TestCase):
    """The vocabulary is derived from the registry, not written beside it."""

    def test_every_registry_field_becomes_a_term(self) -> None:
        from backend.app.services.ingestion import schema_registry as registry

        expected = sum(len(spec.all_fields) for spec in registry.DATASET_SPECS.values())
        self.assertEqual(len(platform_terms()), expected)

    def test_canonical_names_are_unique_per_field(self) -> None:
        # ``river`` really is declared by two data types; the term list keeps
        # both, so uniqueness is asserted on the (type, canonical) pair.
        seen = {(term.data_type, term.canonical) for term in platform_terms()}
        self.assertEqual(len(seen), len(platform_terms()))

    def test_an_alias_two_fields_claim_is_dropped(self) -> None:
        # ``temperature`` is an alias of both water_temp and air_temp. Assigning
        # it to either would be a guess, and a guess here becomes a fabricated
        # provenance edge, so it is dropped from both.
        for canonical in ("water_temp", "air_temp"):
            self.assertNotIn("temperature", terms_by_canonical()[canonical].surfaces)

    def test_label_and_canonical_always_survive(self) -> None:
        term = terms_by_canonical()["air_temp"]
        self.assertIn("平均气温", term.surfaces)
        self.assertIn("air_temp", term.surfaces)


class AlignmentTest(unittest.TestCase):
    """Token alignment: what the field names, and what it must not."""

    def setUp(self) -> None:
        self.bridge = PlatformVocabulary()

    def primary(self, entity_name: str) -> list[str]:
        matches = self.bridge.bridges_to([entity_name]).get(entity_name, [])
        best = max((match.coverage for match in matches), default=0.0)
        return sorted(match.term.canonical for match in matches if match.coverage == best)

    def test_a_field_names_the_entity_that_is_its_name(self) -> None:
        self.assertEqual(self.primary("AIR TEMPERATURE"), ["air_temp"])
        self.assertEqual(self.primary("ANNUAL WIND SPEED"), ["wind_speed"])
        self.assertEqual(self.primary("AMMONIA NITROGEN (NH3-N)"), ["nh3_n"])

    def test_a_qualifier_on_the_entity_does_not_block_the_match(self) -> None:
        # Subsequence, not prefix: the graph's own names carry qualifiers the
        # registry does not.
        self.assertIn("wind_speed", self.primary("NEAR SURFACE WIND SPEED"))
        self.assertIn("huangdu_water_level_m", self.primary("HUANGDU WATER LEVEL"))

    def test_a_field_that_is_only_half_the_name_is_not_primary(self) -> None:
        # ``air_temp`` reaches TEMPERATURE, but AIR TEMPERATURE is what it
        # names. The distinction is what tells the linker whether the field is
        # already served — and a bare TEMPERATURE honestly names both fields,
        # which is why both appear here and neither is primary on its own.
        matches = self.bridge.bridges_to(["AIR TEMPERATURE"])["AIR TEMPERATURE"]
        self.assertEqual(
            sorted(match.term.canonical for match in matches if match.coverage == 1.0),
            ["air_temp"],
        )
        self.assertEqual(self.primary("TEMPERATURE"), ["air_temp", "water_temp"])

    def test_a_token_that_is_a_minority_of_the_name_is_not_a_match(self) -> None:
        # The dilution guard. Without dominance, ``turbidity`` reaches every
        # research construct that mentions turbidity.
        self.assertEqual(self.bridge.bridges_to(["TURBIDITY HISTESIS PATTERNS"]), {})

    def test_short_tokens_do_not_match_by_prefix(self) -> None:
        # ``do`` is a real registry canonical and a real entity; it must not
        # become DOMESTIC, and ``air`` must not become AIRPORT.
        self.assertEqual(self.bridge.bridges_to(["DOMESTIC WASTEWATER"]), {})
        self.assertEqual(self.bridge.bridges_to(["AIRPORT RUNOFF"]), {})
        self.assertEqual(self.primary("DO"), ["dissolved_oxygen"])

    def test_a_chinese_only_name_never_bridges(self) -> None:
        self.assertEqual(self.bridge.bridges_to(["沉积物"]), {})

    def test_fan_out_is_capped(self) -> None:
        names = [f"FLOW VARIANT {index}" for index in range(MAX_ENTITIES_PER_TERM * 2)]
        bridged = self.bridge.bridges_to(names)
        self.assertLessEqual(len(bridged), MAX_ENTITIES_PER_TERM)


class ExpansionTest(unittest.TestCase):
    """The question side: a prose span that names a registry field."""

    def setUp(self) -> None:
        self.bridge = vocabulary()

    def test_a_column_header_reaches_the_name_prose_uses(self) -> None:
        # The whole reason this module exists: the registry's column is
        # 平均气温, and every person and model that mentions it writes 气温.
        triggers = dict(self.bridge.triggered_by("气温对浊度有什么影响？"))
        self.assertIn("气温", triggers)
        self.assertIn("平均气温", triggers["气温"])

    def test_a_feature_name_matches_by_label_containment(self) -> None:
        self.assertEqual([term.canonical for term in self.bridge.matches("气温")], ["air_temp"])
        self.assertEqual([term.canonical for term in self.bridge.matches("air_temp")], ["air_temp"])

    def test_an_internal_model_construct_matches_nothing(self) -> None:
        # 自净指数 and 年周期正弦分量 are the model's own constructs. There is
        # no literature entity for them, and inventing one is the failure mode.
        self.assertEqual(self.bridge.matches("自净指数"), [])
        self.assertEqual(self.bridge.matches("年周期正弦分量"), [])
        self.assertEqual(self.bridge.expand("自净指数"), [])

    def test_expansion_is_deterministic(self) -> None:
        self.assertEqual(self.bridge.expand("气温"), self.bridge.expand("气温"))


class LexiconIntegrationTest(unittest.TestCase):
    """The bridge as the linker uses it: registered on nodes, and declining."""

    def build_bundle(self, root: Path) -> IndexBundle:
        parquet = root / "create_final_relationships.parquet"
        pd.DataFrame(
            [
                {
                    "source": "AIR TEMPERATURE",
                    "target": "TURBIDITY",
                    "weight": 3.0,
                    "description": "气温升高改变水体浊度",
                    "text_unit_ids": "[]",
                    "id": "r1",
                    "human_readable_id": 1,
                    "source_degree": 5,
                    "target_degree": 593,
                    "rank": 1.5,
                },
                {
                    "source": "WIND SPEED",
                    "target": "TURBIDITY",
                    "weight": 2.0,
                    "description": "风速影响沉积物再悬浮",
                    "text_unit_ids": "[]",
                    "id": "r2",
                    "human_readable_id": 2,
                    "source_degree": 9,
                    "target_degree": 593,
                    "rank": 2.5,
                },
            ]
        ).to_parquet(parquet, index=False)
        source = load_inherited_source(parquet)
        assert source is not None
        return load_index([source])

    def lexicon(self) -> EntityLexicon:
        root = Path(self.tmp.name)
        config = GraphRagConfig()
        lexicon = EntityLexicon(self.build_bundle(root), config)
        lexicon.build()
        return lexicon

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_a_prose_question_reaches_the_entity_the_registry_names(self) -> None:
        seeds = self.lexicon().link("气温如何影响浊度？", max_seeds=12, min_score=0.45)
        by_name = {seed.name: seed for seed in seeds}
        self.assertIn("AIR TEMPERATURE", by_name)
        self.assertEqual(by_name["AIR TEMPERATURE"].matched_via, "platform_vocab")
        # Recorded against the span the question used, not the label it reached.
        self.assertEqual(by_name["AIR TEMPERATURE"].surface, "气温")

    def test_a_field_the_curated_tables_already_cover_is_not_bridged_again(self) -> None:
        # WIND SPEED is already reachable through the synonym table, so the
        # bridge must stay out of it — otherwise the seed budget fills with
        # quieter restatements of a node the link had already found.
        lexicon = self.lexicon()
        self.assertEqual(
            [seed.matched_via for seed in lexicon.link("风速如何影响浊度？", max_seeds=12, min_score=0.45)
             if seed.name == "WIND SPEED"],
            ["synonym"],
        )

    def test_the_bridge_can_be_switched_off(self) -> None:
        root = Path(self.tmp.name)
        lexicon = EntityLexicon(
            self.build_bundle(root), GraphRagConfig(platform_vocabulary=False)
        )
        lexicon.build()
        seeds = lexicon.link("气温如何影响浊度？", max_seeds=12, min_score=0.45)
        self.assertNotIn("AIR TEMPERATURE", {seed.name for seed in seeds})


if __name__ == "__main__":
    unittest.main()
