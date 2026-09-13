"""Index-layer tests for the GraphRAG package.

These cover the layer that has to be right *before* any retrieval happens: the
chunk/occurrence provenance ``save_kg`` now writes, the cache key derived
artifacts hang off, and the two loaders that normalise the platform graph and
the inherited GraphRAG parquet onto one shape.

Retrieval quality is measured separately, against the real repository data, in
``test_graph_rag_eval.py``. Nothing here needs the network or the 18 MB
parquet — the inherited loader is exercised on a synthetic frame with the same
schema.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.index import (
    IndexBundle,
    LocalTfidf,
    content_hash,
    load_index,
    node_key,
    read_chunks,
    read_occurrences,
    split_node_key,
)
from backend.app.services.graph_rag import pipeline
from backend.app.services.graph_rag.lexicon import (
    BILINGUAL,
    JUNK_ENTITIES,
    is_junk_entity,
)
from backend.app.services.graph_rag.sources import (
    INHERITED_SOURCE_ID,
    PLATFORM_SOURCE_ID,
    load_inherited_source,
    load_platform_source,
    resolve_sources,
)
from backend.app.services.kg_service import (
    PROVENANCE_ONLY_KEYS,
    save_kg,
    split_text,
    split_text_with_spans,
)


def write_text_file(root: Path, name: str, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def triple(source: str, relation: str, target: str, evidence: str, chunk_id: str, ordinal: int) -> dict:
    return {
        "source": source,
        "source_type": "水质因子",
        "relation": relation,
        "target": target,
        "target_type": "清澈度指标",
        "evidence": evidence,
        "source_file": "clean_a (4).txt",
        "chunk_id": chunk_id,
        "ordinal": ordinal,
    }


class SplitTextWithSpansTest(unittest.TestCase):
    def test_offsets_are_honest(self) -> None:
        text = "第一段。\n\n第二段更长一些。\n\n第三段。"
        for start, end, chunk in split_text_with_spans(text, max_chars=1200):
            self.assertEqual(text[start:end], chunk)

    def test_default_output_matches_split_text(self) -> None:
        text = "\n".join(f"第{i}段" + "内容" * 20 for i in range(12))
        self.assertEqual(
            split_text(text, max_chars=200),
            [chunk for _s, _e, chunk in split_text_with_spans(text, max_chars=200)],
        )

    def test_no_non_newline_character_is_lost(self) -> None:
        text = "\n".join(f"段落{i}：" + "字" * i for i in range(40))
        stitched = "".join(chunk for _s, _e, chunk in split_text_with_spans(text, max_chars=150))
        self.assertEqual(
            stitched.replace("\n", "").replace(" ", ""),
            text.replace("\n", "").replace(" ", ""),
        )

    def test_oversized_paragraph_is_hard_split(self) -> None:
        # 5000 characters with no paragraph break: the old splitter emitted this
        # as one chunk, which would be sent to the extractor whole and cited
        # whole. It must now be broken up.
        text = "浊" * 5000
        spans = split_text_with_spans(text, max_chars=1200)
        self.assertGreater(len(spans), 1)
        for start, end, chunk in spans:
            self.assertLessEqual(len(chunk), 1200)
            self.assertEqual(text[start:end], chunk)

    def test_overlap_repeats_text_but_only_when_asked(self) -> None:
        text = "浊" * 3000
        no_overlap = split_text_with_spans(text, max_chars=1000, overlap_chars=0)
        self.assertEqual([s for s, _e, _c in no_overlap], [0, 1000, 2000])

        with_overlap = split_text_with_spans(text, max_chars=1000, overlap_chars=200)
        self.assertEqual([s for s, _e, _c in with_overlap], [0, 800, 1600, 2400])


class SaveKgProvenanceTest(unittest.TestCase):
    def test_relations_csv_keeps_its_columns(self) -> None:
        # chunk_id/ordinal ride along so occurrences.jsonl can record them, but
        # relations.csv's shape is a contract — it must not grow columns.
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp)
            save_kg(
                [triple("悬浮物", "影响", "透明度", "证据", "clean_a (4)#0000", 0)],
                kg_dir,
                chunks=[{"chunk_id": "clean_a (4)#0000", "source_file": "clean_a (4).txt",
                         "ordinal": 0, "char_start": 0, "char_end": 4, "text": "证据"}],
            )
            header = (kg_dir / "relations.csv").read_text(encoding="utf-8-sig").splitlines()[0]
            for key in PROVENANCE_ONLY_KEYS:
                self.assertNotIn(key, header)

    def test_occurrences_keep_every_pre_dedupe_row(self) -> None:
        # Two chunks report the same triple. relations.csv dedupes to one row;
        # occurrences.jsonl must keep both, because that is the only record of
        # where the surviving relation actually came from.
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp)
            count = save_kg(
                [
                    triple("悬浮物", "影响", "透明度", "证据一", "f#0000", 0),
                    triple("悬浮物", "影响", "透明度", "证据二", "f#0001", 1),
                ],
                kg_dir,
            )
            self.assertEqual(count, 1)

            # On disk the keys are plain entity names — namespacing is applied
            # by the loader, which is what the second half of this test checks.
            rows = read_occurrences(kg_dir / "occurrences.jsonl")[("悬浮物", "影响", "透明度")]
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["chunk_id"] for row in rows}, {"f#0000", "f#0001"})

            source = load_platform_source(kg_dir, None)
            assert source is not None
            self.assertEqual(len(source.occurrences[source.relations[0].key]), 2)

    def test_chunks_and_index_metadata_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp)
            chunks = [
                {"chunk_id": "f#0000", "source_file": "f.txt", "ordinal": 0,
                 "char_start": 0, "char_end": 3, "text": "一二三"},
            ]
            save_kg([triple("甲", "影响", "乙", "证据", "f#0000", 0)], kg_dir, chunks=chunks)

            payload = json.loads((kg_dir / "kg_index.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["n_chunks"], 1)
            self.assertEqual(payload["n_occurrences"], 1)
            self.assertEqual(payload["n_relations"], 1)
            self.assertEqual(payload["n_entities"], 2)
            self.assertTrue(payload["content_hash"].startswith("sha1:"))
            self.assertEqual(len(read_chunks(kg_dir / "chunks.jsonl")), 1)

    def test_chunks_are_optional(self) -> None:
        # The two-argument call every existing caller uses must still work, and
        # must not invent a chunks.jsonl.
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp)
            save_kg([{"source": "甲", "source_type": "x", "relation": "影响",
                      "target": "乙", "target_type": "y", "evidence": "e"}], kg_dir)
            self.assertFalse((kg_dir / "chunks.jsonl").exists())

    def test_content_hash_tracks_relations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp)
            save_kg([triple("甲", "影响", "乙", "证据", "f#0000", 0)], kg_dir)
            before = content_hash(kg_dir / "relations.csv", kg_dir / "occurrences.jsonl")

            save_kg(
                [
                    triple("甲", "影响", "乙", "证据", "f#0000", 0),
                    triple("丙", "导致", "丁", "新证据", "f#0001", 1),
                ],
                kg_dir,
            )
            after = content_hash(kg_dir / "relations.csv", kg_dir / "occurrences.jsonl")
            self.assertNotEqual(before, after)

    def test_content_hash_is_stable_for_identical_graphs(self) -> None:
        rows = [triple("甲", "影响", "乙", "证据", "f#0000", 0)]
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            save_kg(list(rows), Path(first))
            save_kg(list(rows), Path(second))
            self.assertEqual(
                content_hash(Path(first) / "relations.csv", Path(first) / "occurrences.jsonl"),
                content_hash(Path(second) / "relations.csv", Path(second) / "occurrences.jsonl"),
            )

    def test_missing_files_hash_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(
                content_hash(Path(tmp) / "nope.csv", None).startswith("sha1:")
            )


class PlatformSourceTest(unittest.TestCase):
    def test_loads_relations_chunks_and_occurrences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp)
            save_kg(
                [triple("悬浮物", "影响", "透明度", "悬浮物降低透明度", "f#0000", 0)],
                kg_dir,
                chunks=[{"chunk_id": "f#0000", "source_file": "f.txt", "ordinal": 0,
                         "char_start": 0, "char_end": 8, "text": "悬浮物降低透明度"}],
            )

            source = load_platform_source(kg_dir, None)
            self.assertIsNotNone(source)
            assert source is not None
            self.assertEqual(source.relation_count, 1)
            self.assertTrue(source.chunk_level)
            self.assertEqual(source.label_key, "kg.source.runtime")

            relation = source.relations[0]
            self.assertEqual(relation.display_source, "悬浮物")
            self.assertEqual(relation.display_target, "透明度")

            # Occurrence lookups go through the namespaced key, same as the
            # relation's own key.
            self.assertIn(relation.key, source.occurrences)

    def test_runtime_wins_over_baseline_without_merging(self) -> None:
        rows = [triple("甲", "影响", "乙", "证据", "f#0000", 0)]
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            baseline = Path(tmp) / "baseline"
            save_kg(list(rows), runtime)
            save_kg(list(rows) + [triple("丙", "导致", "丁", "证据", "f#0001", 1)], baseline)

            source = load_platform_source(runtime, baseline)
            assert source is not None
            self.assertEqual(source.relation_count, 1)
            self.assertEqual(source.label_key, "kg.source.runtime")

    def test_falls_back_to_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "baseline"
            save_kg([triple("甲", "影响", "乙", "证据", "f#0000", 0)], baseline)

            source = load_platform_source(Path(tmp) / "absent", baseline)
            assert source is not None
            self.assertEqual(source.label_key, "kg.source.baseline")

    def test_absent_everywhere_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_platform_source(Path(tmp) / "a", Path(tmp) / "b"))


class InheritedSourceTest(unittest.TestCase):
    """The parquet has no relation-type column; ``description`` *is* the relation."""

    def build_parquet(self, path: Path) -> None:
        frame = pd.DataFrame(
            [
                {
                    "source": "TURBIDITY",
                    "target": "TURBIDIMETERS",
                    "weight": 3.0,
                    "description": "浊度计用于测量水体浊度",
                    "text_unit_ids": "[]",
                    "id": "r1",
                    "human_readable_id": 1,
                    "source_degree": 593,
                    "target_degree": 12,
                    "rank": 1.5,
                },
                {
                    "source": "AGRICULTURE",
                    "target": "SEDIMENT",
                    "weight": 2.0,
                    "description": "农业活动是土壤侵蚀和沉积物负荷增加的主要原因",
                    "text_unit_ids": "[]",
                    "id": "r2",
                    "human_readable_id": 2,
                    "source_degree": 40,
                    "target_degree": 55,
                    "rank": 2.5,
                },
            ]
        )
        frame.to_parquet(path, index=False)

    def test_maps_description_onto_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "create_final_relationships.parquet"
            self.build_parquet(path)

            source = load_inherited_source(path)
            assert source is not None
            self.assertEqual(source.relation_count, 2)
            self.assertFalse(source.chunk_level)
            self.assertEqual(source.label_key, "kg.source.inherited")

            relation = source.relations[0]
            self.assertEqual(relation.relation, "")
            self.assertEqual(relation.evidence, "浊度计用于测量水体浊度")
            self.assertIsNone(relation.chunk_id)
            self.assertEqual(relation.source_degree, 593)
            # No relation label: the short form is endpoints only, and the
            # description is rendered once as the evidence rather than being
            # inlined here as well.
            self.assertEqual(relation.display(), "TURBIDITY → TURBIDIMETERS")

    def test_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_inherited_source(Path(tmp) / "absent.parquet"))

    def test_missing_required_column_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.parquet"
            pd.DataFrame([{"source": "A", "target": "B"}]).to_parquet(path, index=False)
            self.assertIsNone(load_inherited_source(path))


class NamespacingTest(unittest.TestCase):
    def test_sources_cannot_collide(self) -> None:
        self.assertNotEqual(
            node_key(PLATFORM_SOURCE_ID, "沉积物"),
            node_key(INHERITED_SOURCE_ID, "沉积物"),
        )
        self.assertEqual(split_node_key(node_key("x", "a::b")), ("x", "a::b"))

    def test_prefix_never_leaks_into_lexical_text(self) -> None:
        # A namespaced key in the n-gram corpus would make "platform" a matching
        # term for every platform relation.
        self.build_and_check()

    def build_and_check(self) -> None:
        rows = [triple("悬浮物", "影响", "透明度", "悬浮物降低透明度", "f#0000", 0)]
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp)
            save_kg(list(rows), kg_dir)
            bundle = load_index([load_platform_source(kg_dir, None)])
            relation = bundle.sources[PLATFORM_SOURCE_ID].relations[0]
            self.assertNotIn(PLATFORM_SOURCE_ID, relation.lexical_text())
            self.assertNotIn("::", relation.as_dict()["source"])


class JunkEntityTest(unittest.TestCase):
    def test_bibliographic_nodes_are_flagged(self) -> None:
        for name in ("REFERENCE", "PARAMETER", "MODEL", "DATA", "YEAR", "STUDY"):
            self.assertTrue(is_junk_entity(name), name)

    def test_real_acronyms_are_not_flagged(self) -> None:
        # These look like graph noise and are not: they are the entities the
        # water-quality questions in the eval fixture depend on.
        for name in ("TSS", "SSC", "DO", "PH", "TP", "TN", "COD", "BOD"):
            self.assertFalse(is_junk_entity(name), name)
            self.assertNotIn(name, JUNK_ENTITIES)

    def test_bilingual_covers_the_domain_vocabulary(self) -> None:
        for english, chinese in (
            ("TURBIDITY", "浊度"),
            ("SSC", "悬浮物浓度"),
            ("TOTAL PHOSPHORUS (TP)", "总磷"),
            ("AGRICULTURE", "农业"),
        ):
            self.assertIn(chinese, BILINGUAL[english])


class IndexBundleTest(unittest.TestCase):
    def test_has_chunks_is_false_without_a_chunks_file(self) -> None:
        # The shipped baseline can never support chunk-level citations — its
        # source text is gone. The bundle has to say so rather than pretend.
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp)
            save_kg([triple("甲", "影响", "乙", "证据", "f#0000", 0)], kg_dir)
            # Drop the chunk file and the occurrence provenance: this is exactly
            # the baseline's shape.
            (kg_dir / "occurrences.jsonl").unlink()

            bundle = load_index([load_platform_source(kg_dir, None)])
            self.assertFalse(bundle.has_chunks)
            self.assertFalse(bundle.capabilities()["chunk_level"])
            self.assertTrue(bundle.notes)

    def test_has_chunks_is_true_after_a_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp)
            save_kg(
                [triple("甲", "影响", "乙", "证据", "f#0000", 0)],
                kg_dir,
                chunks=[{"chunk_id": "f#0000", "source_file": "f.txt", "ordinal": 0,
                         "char_start": 0, "char_end": 2, "text": "证据"}],
            )
            bundle = load_index([load_platform_source(kg_dir, None)])
            self.assertTrue(bundle.has_chunks)
            self.assertEqual(len(bundle.all_chunks()), 1)

    def test_occurrence_chunks_resolve_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp)
            save_kg(
                [
                    triple("甲", "影响", "乙", "证据", "f#0000", 0),
                    triple("甲", "影响", "乙", "证据", "f#0000", 0),
                    triple("甲", "影响", "乙", "证据", "f#0001", 1),
                ],
                kg_dir,
                chunks=[
                    {"chunk_id": "f#0000", "source_file": "f.txt", "ordinal": 0,
                     "char_start": 0, "char_end": 2, "text": "证据"},
                    {"chunk_id": "f#0001", "source_file": "f.txt", "ordinal": 1,
                     "char_start": 3, "char_end": 5, "text": "证据"},
                ],
            )
            source = load_platform_source(kg_dir, None)
            assert source is not None
            bundle = IndexBundle(sources={PLATFORM_SOURCE_ID: source}, order=[PLATFORM_SOURCE_ID])

            found = bundle.occurrence_chunks(PLATFORM_SOURCE_ID, source.relations[0].key, limit=5)
            self.assertEqual([item["chunk"].chunk_id for item in found], ["f#0000", "f#0001"])
            self.assertEqual(
                [item["chunk"].chunk_id
                 for item in bundle.occurrence_chunks(PLATFORM_SOURCE_ID, source.relations[0].key, 1)],
                ["f#0000"],
            )

    def test_empty_bundle_is_empty(self) -> None:
        bundle = load_index([])
        self.assertTrue(bundle.is_empty)
        self.assertEqual(bundle.relation_count, 0)
        self.assertFalse(bundle.has_chunks)

    def test_describe_sources_reports_both(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kg_dir = tmp_path / "kg"
            save_kg([triple("甲", "影响", "乙", "证据", "f#0000", 0)], kg_dir)

            parquet = tmp_path / "create_final_relationships.parquet"
            pd.DataFrame([{"source": "A", "target": "B", "description": "描述"}]).to_parquet(
                parquet, index=False
            )

            sources = resolve_sources(
                config=GraphRagConfig(),
                runtime_dir=kg_dir,
                baseline_dir=None,
                inherited_path=parquet,
            )
            self.assertEqual([source.source_id for source in sources],
                             [PLATFORM_SOURCE_ID, INHERITED_SOURCE_ID])

            described = load_index(sources).describe_sources()
            self.assertEqual([item["source_id"] for item in described],
                             [PLATFORM_SOURCE_ID, INHERITED_SOURCE_ID])
            self.assertEqual(described[1]["relation_count"], 1)

    def test_sources_can_be_narrowed_by_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kg_dir = Path(tmp) / "kg"
            save_kg([triple("甲", "影响", "乙", "证据", "f#0000", 0)], kg_dir)
            sources = resolve_sources(
                config=GraphRagConfig().with_overrides(sources=("platform",)),
                runtime_dir=kg_dir,
                baseline_dir=None,
                project_root=Path(tmp),
            )
            self.assertEqual([source.source_id for source in sources], [PLATFORM_SOURCE_ID])


class LocalTfidfTest(unittest.TestCase):
    def test_char_ngrams_match_across_scripts(self) -> None:
        # The point of char_wb: a Chinese query reaches Chinese text without a
        # tokenizer, and the same vector space holds the English entity names.
        retriever = LocalTfidf(ngram_max=3)
        retriever.add("r#0", "TURBIDITY TURBIDIMETERS 浊度计用于测量水体浊度")
        retriever.add("r#1", "AGRICULTURE SEDIMENT 农业活动是土壤侵蚀的主要原因")

        scores = retriever.scores("浊度计如何测量浊度")
        self.assertEqual(len(scores), len(retriever.doc_ids))
        self.assertGreater(scores[0], scores[1])

    def test_unknown_query_scores_zero_everywhere(self) -> None:
        retriever = LocalTfidf(ngram_max=3)
        retriever.add("r#0", "透明度")
        scores = retriever.scores("完全不相关的量子色动力学")
        self.assertEqual(float(scores[0]), 0.0)

    def test_empty_index_is_safe(self) -> None:
        self.assertEqual(len(LocalTfidf().scores("任何问题")), 0)

    def test_duplicate_add_is_ignored(self) -> None:
        retriever = LocalTfidf()
        retriever.add("r#0", "甲")
        retriever.add("r#0", "乙")
        self.assertEqual(retriever.size, 1)
        self.assertEqual(retriever.position("r#0"), 0)
        self.assertIsNone(retriever.position("r#1"))
        self.assertEqual(retriever.score_one("甲", "r#1"), 0.0)


class DeterministicSummaryTest(unittest.TestCase):
    """The digest the agent-injection path sends, built with no model call."""

    @staticmethod
    def _result() -> dict:
        return {
            "mode": "local",
            "matched_relations": [
                {"source": "底泥再悬浮", "relation": "增加", "target": "浊度"},
                {"source": "AGRICULTURE", "relation": "", "target": "SEDIMENT",
                 "evidence": "农业活动是土壤侵蚀的主要原因"},
            ],
            "paths": [{"nodes": ["风", "沉积物再悬浮", "浊度"]}],
            "stats": {"seed_count": 2, "path_count": 1},
        }

    def test_it_states_the_mode_the_counts_and_the_edges(self) -> None:
        summary = pipeline.deterministic_summary(self._result())
        self.assertIn("检索模式：local", summary)
        self.assertIn("命中 2 个实体、1 条路径", summary)
        self.assertIn("- 底泥再悬浮 --增加--> 浊度", summary)
        # An edge with no relation label falls back to its description — the
        # inherited graph has no relation types at all.
        self.assertIn("- AGRICULTURE --农业活动是土壤侵蚀的主要原因--> SEDIMENT", summary)
        self.assertIn("关联链路：风 → 沉积物再悬浮 → 浊度", summary)

    def test_the_edge_listing_can_be_left_out(self) -> None:
        """The agent context sends the edges as data; stating them twice is waste."""
        summary = pipeline.deterministic_summary(self._result(), include_relations=False)
        self.assertNotIn("相关图谱关系", summary)
        self.assertNotIn("底泥再悬浮 --增加--> 浊度", summary)
        # What the edges do not carry — the counts and the multi-hop chain —
        # survives, which is the whole reason the summary is still sent.
        self.assertIn("检索模式：local", summary)
        self.assertIn("关联链路：风 → 沉积物再悬浮 → 浊度", summary)

    def test_a_cap_is_respected(self) -> None:
        self.assertLessEqual(len(pipeline.deterministic_summary(self._result(), 40)), 40)

    def test_a_result_with_nothing_in_it_still_says_so(self) -> None:
        """Zero hits is information the agent should be told, not silence.

        A summary that came back empty would leave the caller unable to tell
        "the graph had nothing" from "retrieval was never run".
        """
        summary = pipeline.deterministic_summary({"mode": "none", "matched_relations": []})
        self.assertIn("检索模式：none", summary)
        self.assertIn("命中 0 个实体、0 条路径", summary)


class ConfigTest(unittest.TestCase):
    def test_defaults(self) -> None:
        config = GraphRagConfig()
        self.assertEqual(config.sources, ("platform", "inherited"))
        self.assertEqual(config.depth_for("platform"), 2)
        self.assertEqual(config.depth_for("inherited"), 1)
        self.assertEqual(config.prior_for("platform"), 1.0)
        self.assertGreater(config.prior_for("platform"), config.prior_for("inherited"))
        self.assertEqual(config.prior_for("unknown"), 1.0)

    def test_from_env_reads_values(self) -> None:
        config = GraphRagConfig.from_env(
            {
                "WATEREXPERT_GRAPH_RAG_SOURCES": "platform",
                "WATEREXPERT_GRAPH_RAG_TOP_K": "3",
                "WATEREXPERT_GRAPH_RAG_W_LEX": "0.9",
                "WATEREXPERT_GRAPH_RAG_COMMUNITIES_ENABLED": "off",
                "WATEREXPERT_GRAPH_RAG_SOURCE_PRIOR": "platform=1.0,inherited=0.5",
            }
        )
        self.assertEqual(config.sources, ("platform",))
        self.assertEqual(config.top_k, 3)
        self.assertAlmostEqual(config.w_lex, 0.9)
        self.assertFalse(config.communities_enabled)
        self.assertAlmostEqual(config.prior_for("inherited"), 0.5)

    def test_from_env_ignores_garbage(self) -> None:
        # A typo in a tuning knob must not take the service down.
        config = GraphRagConfig.from_env(
            {
                "WATEREXPERT_GRAPH_RAG_TOP_K": "not-a-number",
                "WATEREXPERT_GRAPH_RAG_SOURCE_PRIOR": "garbage",
            }
        )
        self.assertEqual(config.top_k, GraphRagConfig().top_k)
        self.assertEqual(config.prior_for("inherited"), GraphRagConfig().prior_for("inherited"))

    def test_hop_depth_is_capped(self) -> None:
        config = GraphRagConfig().with_overrides(hop_depth={"platform": 99}, max_hop_depth=3)
        self.assertEqual(config.depth_for("platform"), 3)

    def test_hop_depth_has_a_floor(self) -> None:
        config = GraphRagConfig().with_overrides(hop_depth={"platform": 0})
        self.assertEqual(config.depth_for("platform"), 1)


class RunnerChunkIdTest(unittest.TestCase):
    """``chunk_id`` is what a citation points at, so it has to be stable."""

    def test_ids_are_deterministic_and_ordered(self) -> None:
        from backend.app.tasks.kg_job_runner import KgJobRunnerArgs, load_chunks

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_dir = root / "text"
            write_text_file(text_dir, "clean_a (4).txt", "\n\n".join(f"第{i}段内容" * 10 for i in range(5)))

            args = KgJobRunnerArgs(
                kg_dir=root / "kg",
                text_dir=text_dir,
                status_file=root / "status.json",
                selected_files=["clean_a (4).txt"],
                max_chars=1200,
            )
            first = load_chunks(args)
            second = load_chunks(args)

            self.assertEqual([chunk.chunk_id for chunk in first],
                             [chunk.chunk_id for chunk in second])
            self.assertEqual(first[0].chunk_id, "clean_a (4)#0000")
            self.assertEqual([chunk.ordinal for chunk in first], list(range(len(first))))
            for chunk in first:
                self.assertEqual(chunk.source_file, "clean_a (4).txt")

    def test_ids_do_not_collide_across_files(self) -> None:
        from backend.app.tasks.kg_job_runner import KgJobRunnerArgs, load_chunks

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_dir = root / "text"
            write_text_file(text_dir, "a.txt", "第一份内容")
            write_text_file(text_dir, "b.txt", "第二份内容")

            chunks = load_chunks(
                KgJobRunnerArgs(
                    kg_dir=root / "kg",
                    text_dir=text_dir,
                    status_file=root / "status.json",
                    selected_files=["a.txt", "b.txt"],
                    max_chars=1200,
                )
            )
            self.assertEqual({chunk.chunk_id for chunk in chunks}, {"a#0000", "b#0000"})

    def test_missing_file_raises(self) -> None:
        from backend.app.tasks.kg_job_runner import KgJobRunnerArgs, load_chunks

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                load_chunks(
                    KgJobRunnerArgs(
                        kg_dir=root / "kg",
                        text_dir=root / "text",
                        status_file=root / "status.json",
                        selected_files=["absent.txt"],
                        max_chars=1200,
                    )
                )


class CommunityMaterialisationTest(unittest.TestCase):
    """The build-time community phase, and the cost claim attached to it.

    ``communities.json`` is the only community artifact a question ever reads.
    These tests pin the three properties that make that safe: the phase is free
    when no model is configured, a failed model call degrades to the extractive
    summary rather than failing the build, and a cached summary is only reused
    while it still describes the graph it was written for.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _source(self, *, extra_edges: int = 0):
        """A small graph with an obvious two-cluster structure."""
        triples = [
            triple("风", "影响", "浊度", "风致扰动使浊度升高", "a#0000", 0),
            triple("浊度", "监测", "悬浮物浓度", "浊度可反演悬浮物浓度", "a#0000", 0),
            triple("悬浮物浓度", "影响", "透明度", "悬浮物降低透明度", "a#0001", 1),
        ]
        for index in range(extra_edges):
            triples.append(
                triple(f"营养盐{index}", "影响", "叶绿素a", f"营养盐{index}促进藻类生长", "a#0002", 2)
            )
        kg_dir = self.root / "kg"
        save_kg(triples, kg_dir, chunks=[{"chunk_id": "a#0000", "text": "原文"}])
        return load_platform_source(kg_dir, None), kg_dir

    def test_writes_communities_and_reports_them(self) -> None:
        from backend.app.services.graph_rag.global_search import (
            COMMUNITIES_FILE,
            load_communities,
            materialise_source_communities,
        )

        source, kg_dir = self._source()
        communities = materialise_source_communities(source, GraphRagConfig(), kg_dir)

        self.assertTrue(communities)
        stored = load_communities(kg_dir / COMMUNITIES_FILE)
        self.assertEqual(len(stored[PLATFORM_SOURCE_ID]), len(communities))
        # ``node_keys`` has to survive the round trip: the coverage signal
        # compares members against namespaced seed keys, so a payload that
        # dropped it would silently disable one of the two ranking signals.
        entry = stored[PLATFORM_SOURCE_ID][0]
        self.assertTrue(entry["node_keys"])
        self.assertTrue(all(key.startswith(f"{PLATFORM_SOURCE_ID}::") for key in entry["node_keys"]))

    def test_no_model_configuration_writes_no_summaries_file(self) -> None:
        from backend.app.services.graph_rag.global_search import (
            COMMUNITIES_FILE,
            SUMMARIES_FILE,
            materialise_source_communities,
        )

        source, kg_dir = self._source()
        calls: list[str] = []
        materialise_source_communities(
            source,
            GraphRagConfig(),
            kg_dir,
            call_llm=None,
        )
        self.assertEqual(calls, [])
        self.assertTrue((kg_dir / COMMUNITIES_FILE).exists())
        self.assertFalse(
            (kg_dir / SUMMARIES_FILE).exists(),
            "an all-extractive run has nothing to cache — the question path can "
            "always recompute it for free",
        )

    def test_summaries_are_capped_and_cached_under_the_content_hash(self) -> None:
        from backend.app.services.graph_rag.global_search import (
            SUMMARIES_FILE,
            materialise_source_communities,
            read_summaries,
        )

        source, kg_dir = self._source(extra_edges=8)
        config = GraphRagConfig().with_overrides(community_max_llm_calls=2)
        prompts: list[str] = []

        def fake_llm(prompt: str) -> str:
            prompts.append(prompt)
            return "模型摘要。"

        materialise_source_communities(
            source, config, kg_dir, content_hash_value="sha1:abc", call_llm=fake_llm
        )
        self.assertEqual(len(prompts), 2, "the LLM budget is per rebuild, not per community")

        cached = read_summaries(kg_dir / SUMMARIES_FILE, "sha1:abc")
        self.assertTrue(cached)
        self.assertTrue(any(entry["mode"] == "llm" for entry in cached.values()))
        # A rebuild changed the graph, so the cache describes something that no
        # longer exists. Reusing it would cite a community that has moved.
        self.assertEqual(read_summaries(kg_dir / SUMMARIES_FILE, "sha1:def"), {})

    def test_a_failing_model_still_yields_a_usable_summary(self) -> None:
        from backend.app.services.graph_rag.global_search import (
            materialise_source_communities,
        )

        source, kg_dir = self._source()

        def broken_llm(_prompt: str) -> str:
            raise RuntimeError("429 rate limited")

        communities = materialise_source_communities(
            source, GraphRagConfig().with_overrides(community_max_llm_calls=3),
            kg_dir, call_llm=broken_llm,
        )
        self.assertTrue(communities)
        for community in communities:
            self.assertEqual(community["summary_mode"], "extractive")
            self.assertIn("该社区包含", community["summary"])

    def test_rewriting_one_source_leaves_the_other_alone(self) -> None:
        """The file holds one entry per source, and only one of them rebuilds.

        The inherited graph has no build step of its own to put its partition
        back, so a platform rebuild that dropped it would cost a detection pass
        on every cold start, forever.
        """
        from backend.app.services.graph_rag.global_search import (
            COMMUNITIES_FILE,
            load_communities,
            materialise_source_communities,
            write_communities,
        )

        source, kg_dir = self._source()
        foreign = [
            {
                "community_id": "inherited:c0001",
                "source_id": "inherited",
                "size": 3,
                "nodes": ["TURBIDITY"],
                "node_keys": ["inherited::TURBIDITY"],
                "top_relations": [],
            }
        ]
        write_communities(kg_dir / COMMUNITIES_FILE, foreign)

        materialise_source_communities(source, GraphRagConfig(), kg_dir)

        groups = load_communities(kg_dir / COMMUNITIES_FILE)
        self.assertIn(PLATFORM_SOURCE_ID, groups)
        self.assertEqual(groups["inherited"], foreign)

    def test_disabled_communities_write_nothing(self) -> None:
        from backend.app.services.graph_rag.global_search import (
            COMMUNITIES_FILE,
            materialise_source_communities,
        )

        source, kg_dir = self._source()
        result = materialise_source_communities(
            source, GraphRagConfig().with_overrides(communities_enabled=False), kg_dir
        )
        self.assertEqual(result, [])
        self.assertFalse((kg_dir / COMMUNITIES_FILE).exists())


class RunnerCommunityPhaseTest(unittest.TestCase):
    """``build_communities`` must never be the reason a good build reads as failed."""

    def test_returns_zero_when_communities_are_disabled(self) -> None:
        from backend.app.tasks.kg_job_runner import KgJobRunnerArgs, build_communities

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kg_dir = root / "kg"
            kg_dir.mkdir(parents=True)
            count = build_communities(
                KgJobRunnerArgs(
                    kg_dir=kg_dir,
                    text_dir=root / "text",
                    status_file=root / "status.json",
                    selected_files=[],
                    max_chars=1200,
                )
            )
            self.assertEqual(count, 0)

    def test_missing_graph_returns_zero_without_raising(self) -> None:
        from backend.app.tasks.kg_job_runner import KgJobRunnerArgs, build_communities

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kg_dir = root / "kg"
            kg_dir.mkdir(parents=True)
            count = build_communities(
                KgJobRunnerArgs(
                    kg_dir=kg_dir,
                    text_dir=root / "text",
                    status_file=root / "status.json",
                    selected_files=[],
                    max_chars=1200,
                )
            )
            self.assertEqual(count, 0)


class RunnerEndToEndTest(unittest.TestCase):
    """One full build, with the extractor stubbed out.

    This is the only test that exercises the progress contract the build panel
    reads, and the only one that runs ``main`` — the extraction loop and the
    community phase in the order they actually happen.
    """

    def test_progress_reaches_the_ceiling_before_communities_and_ends_at_100(self) -> None:
        import sys
        from unittest import mock

        from backend.app.services import kg_llm
        from backend.app.tasks import kg_job_runner

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_dir = root / "text"
            write_text_file(text_dir, "a.txt", "\n\n".join(f"第{i}段" * 40 for i in range(4)))
            kg_dir = root / "kg"
            status_file = root / "status.json"

            def fake_extract(text: str) -> list[dict]:
                return [triple("风", "影响", "浊度", "风致扰动", "a#0000", 0)]

            argv = [
                "kg_job_runner",
                "--kg-dir", str(kg_dir),
                "--text-dir", str(text_dir),
                "--status-file", str(status_file),
                "--selected-files", json.dumps(["a.txt"]),
                "--max-chars", "1200",
            ]

            observed: list[int] = []
            real_update = kg_job_runner.update_status

            def spy(status_file_arg, **updates):
                if "progress" in updates:
                    observed.append(updates["progress"])
                return real_update(status_file_arg, **updates)

            with mock.patch.object(sys, "argv", argv), \
                 mock.patch.object(kg_job_runner, "extract_triples", fake_extract), \
                 mock.patch.object(kg_job_runner, "update_status", spy), \
                 mock.patch.object(kg_llm, "is_llm_configured", lambda: False):
                exit_code = kg_job_runner.main()

            self.assertEqual(exit_code, 0)
            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["progress"], 100)
            self.assertEqual(status["relation_count"], 1)
            self.assertGreater(status["community_count"], 0)

            # Extraction never claims the community phase's last tenth: the
            # ceiling is the highest progress any *running* update reports, and
            # the final 100 is written once, on completion.
            self.assertIn(kg_job_runner.EXTRACTION_CEILING, observed)
            self.assertEqual(observed, sorted(observed))
            self.assertEqual(max(observed), kg_job_runner.EXTRACTION_CEILING)
            self.assertLess(observed[-1], 100)

            self.assertTrue((kg_dir / "communities.json").exists())
            self.assertFalse(
                (kg_dir / "summaries.json").exists(),
                "no key is configured, so there is nothing to cache",
            )


if __name__ == "__main__":
    unittest.main()
