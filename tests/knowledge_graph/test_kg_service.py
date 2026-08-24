from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from backend.app.config import Settings
from backend.app.services.kg_service import (
    KnowledgeGraphService,
    build_extraction_prompt,
    extract_keywords,
    fallback_answer,
    load_relations,
    parse_json,
    retrieve_graph_context,
    save_kg,
    score_relation,
    split_text,
)


def make_settings(tmp_root: Path) -> Settings:
    return Settings(
        app_name="test",
        project_root=tmp_root,
        runtime_root=tmp_root,
        frontend_root=tmp_root / "frontend" / "out",
        report_root=tmp_root / "var" / "reports",
        state_root=tmp_root / "var" / "state",
    )


class SplitTextTest(unittest.TestCase):
    def test_respects_max_chars_and_preserves_content(self) -> None:
        text = "\n".join(f"第{i}段" * 50 for i in range(10))
        chunks = split_text(text, max_chars=200)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 300 for chunk in chunks))
        self.assertEqual("".join(chunks).replace("\n", ""), text.replace("\n", ""))

    def test_short_text_is_single_chunk(self) -> None:
        chunks = split_text("透明度监测", max_chars=1200)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].strip(), "透明度监测")


class ParseJsonTest(unittest.TestCase):
    def test_plain_json(self) -> None:
        self.assertEqual(parse_json('{"triples": []}'), {"triples": []})

    def test_json_wrapped_in_prose(self) -> None:
        text = '以下是结果：\n```json\n{"triples": [{"source": "A"}]}\n```'
        self.assertEqual(parse_json(text)["triples"][0]["source"], "A")

    def test_invalid_returns_empty_triples(self) -> None:
        self.assertEqual(parse_json("无法解析"), {"triples": []})


class BuildPromptTest(unittest.TestCase):
    def test_prompt_contains_chunk_and_instruction(self) -> None:
        prompt = build_extraction_prompt("透明度受悬浮物影响")
        self.assertIn("透明度受悬浮物影响", prompt)
        self.assertIn("三元组", prompt)


class SaveAndLoadKgTest(unittest.TestCase):
    def test_save_kg_writes_files_and_dedupes(self) -> None:
        triples = [
            {
                "source": "悬浮物",
                "source_type": "水质因子",
                "relation": "影响",
                "target": "透明度",
                "target_type": "清澈度指标",
                "evidence": "悬浮物影响透明度",
            },
            {
                "source": "悬浮物",
                "source_type": "水质因子",
                "relation": "影响",
                "target": "透明度",
                "target_type": "清澈度指标",
                "evidence": "重复条目",
            },
            {
                "source": "风速",
                "source_type": "环境因子",
                "relation": "导致",
                "target": "沉积物再悬浮",
                "target_type": "水质因子",
                "evidence": "风致再悬浮",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            count = save_kg(triples, Path(tmp_dir))

            self.assertEqual(count, 2)  # one duplicate removed

            entities_path = Path(tmp_dir) / "entities.csv"
            relations_path = Path(tmp_dir) / "relations.csv"
            graph_path = Path(tmp_dir) / "graph.json"

            self.assertTrue(entities_path.exists())
            self.assertTrue(relations_path.exists())
            self.assertTrue(graph_path.exists())

            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            self.assertEqual(len(graph["nodes"]), 4)
            self.assertEqual(len(graph["edges"]), 2)

            loaded = load_relations(relations_path)
            self.assertEqual(len(loaded), 2)

    def test_load_relations_handles_bom_and_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "relations.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["source", "source_type", "relation", "target", "target_type", "evidence"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "source": "悬浮物",
                        "source_type": "水质因子",
                        "relation": "影响",
                        "target": "透明度",
                        "target_type": "清澈度指标",
                        "evidence": "证据",
                    }
                )

            rows = load_relations(path)
            self.assertEqual(rows[0]["source"], "悬浮物")

        self.assertEqual(load_relations(None), [])
        self.assertEqual(load_relations(Path("/nonexistent/relations.csv")), [])


class RetrievalTest(unittest.TestCase):
    def test_extract_keywords_finds_domain_terms_and_english(self) -> None:
        keywords = extract_keywords("监测 TSS 的方法")
        self.assertIn("监测", keywords)
        self.assertIn("TSS", keywords)

    def test_score_relation_rewards_question_overlap(self) -> None:
        row = {
            "source": "悬浮物",
            "target": "透明度",
            "relation": "影响",
            "evidence": "悬浮物影响透明度",
        }
        question = "悬浮物如何影响透明度？"
        score = score_relation(row, question, ["悬浮物", "透明度"])
        self.assertGreater(score, 0)

    def test_retrieve_graph_context_returns_sorted_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "relations.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["source", "source_type", "relation", "target", "target_type", "evidence"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "source": "悬浮物",
                        "source_type": "水质因子",
                        "relation": "影响",
                        "target": "透明度",
                        "target_type": "清澈度指标",
                        "evidence": "悬浮物影响透明度",
                    }
                )
                writer.writerow(
                    {
                        "source": "风速",
                        "source_type": "环境因子",
                        "relation": "导致",
                        "target": "沉积物再悬浮",
                        "target_type": "水质因子",
                        "evidence": "风致再悬浮",
                    }
                )

            matched = retrieve_graph_context("悬浮物如何影响透明度？", path, top_k=8)

            self.assertTrue(matched)
            self.assertEqual(matched[0]["source"], "悬浮物")
            self.assertIn("_score", matched[0])

    def test_fallback_answer_lists_relations(self) -> None:
        answer = fallback_answer(
            "透明度受什么影响？",
            [{"source": "悬浮物", "relation": "影响", "target": "透明度", "evidence": "证据"}],
        )
        self.assertIn("悬浮物", answer)
        self.assertIn("透明度", answer)


class KnowledgeGraphServiceTest(unittest.TestCase):
    def test_summary_and_graph_with_empty_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = KnowledgeGraphService(make_settings(Path(tmp_dir)))

            summary = service.summary()
            self.assertEqual(summary["uploads"], 0)
            self.assertEqual(summary["texts"], 0)
            self.assertEqual(summary["node_count"], 0)
            self.assertEqual(summary["edge_count"], 0)
            self.assertEqual(summary["source"], "none")

            graph = service.graph()
            self.assertEqual(graph["nodes"], [])
            self.assertEqual(graph["source"], "none")

    def test_file_download_path_rejects_unknown_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = KnowledgeGraphService(make_settings(Path(tmp_dir)))
            with self.assertRaises(FileNotFoundError):
                service.file_download_path("unknown.txt")

    def test_clear_kg_removes_runtime_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = KnowledgeGraphService(make_settings(Path(tmp_dir)))

            save_kg(
                [
                    {
                        "source": "悬浮物",
                        "source_type": "水质因子",
                        "relation": "影响",
                        "target": "透明度",
                        "target_type": "清澈度指标",
                        "evidence": "证据",
                    }
                ],
                service.kg_dir,
            )
            self.assertEqual(service.graph()["source"], "runtime")

            deleted = service.clear_kg()
            self.assertGreaterEqual(deleted, 3)  # entities.csv, relations.csv, graph.json

            self.assertEqual(service.graph()["source"], "none")
            self.assertEqual(service.graph()["node_count"], 0)


if __name__ == "__main__":
    unittest.main()
