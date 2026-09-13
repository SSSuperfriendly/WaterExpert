"""Retrieval-quality evaluation: GraphRAG against the scorer it replaces.

This module answers one question — *did the knowledge graph actually make
retrieval better?* — and it answers it against the real repository data, not a
synthetic graph. It runs the **same fixture** twice, once through the old path
(``kg_service.retrieve_graph_context`` + ``score_relation``) and once through
``graph_rag``, and prints the full per-question table with ``-s``.

Two things about it are deliberately unglamorous:

**The gate is on the aggregate, not per question.** On an 87-edge graph, an
assertion that every metric improves on every question is noise that gets
disabled within a week. The per-question numbers are printed for a human; the
assertions cover the means, with a tolerance.

**The baseline is reported split by source, and the split is the finding.** The
legacy scorer reads only ``relations.csv`` — the platform graph — so no
inherited relation can ever come back through it. That is a structural fact,
not a ranking result. Averaging it into one number would overstate the win, so
the platform-only column is reported as the measure of retrieval quality on the
graph both paths can see, and the inherited column as the measure of the thing
that did not exist before.

**One column genuinely regresses, and it is recorded rather than smoothed.** On
the platform-only questions GraphRAG scores below ``score_relation``: that
scorer's integer table (+10/+10/+8/+6/+5/+2/+8/−3) was hand-tuned on exactly
these 87 edges, most of its weight rides on literal relation-word matches, and
the fixture's platform questions were written by reading those same edges. The
gate below therefore bounds the deficit at a declared constant instead of
asserting a win that did not happen — see ``PLATFORM_RECALL_GAP``.

No network: ``zero_llm_calls`` makes any model call an error, which is also the
mechanical proof of the plan's cost claim — GraphRAG adds zero LLM calls per
question.
"""

from __future__ import annotations

import itertools
import json
import math
import statistics
import unittest
from pathlib import Path
from typing import Any

import pytest

from backend.app.services import kg_service as legacy
from backend.app.services.graph_rag.config import GraphRagConfig
from backend.app.services.graph_rag.pipeline import search

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "graph_rag_eval.jsonl"

RUNTIME_DIR = REPO_ROOT / "var" / "knowledge_graph"
BASELINE_DIR = REPO_ROOT / "outputs" / "knowledge_graph"
INHERITED_PARQUET = REPO_ROOT / "data" / "knowledge_graph" / "create_final_relationships.parquet"

#: ``recall@K`` and the retrieval cut share this number: K is not a free
#: parameter here, it is the size of the window the prompt actually gets.
K = 8

#: How much the aggregates may move before it counts as a regression. Wide
#: enough to absorb a dependency bump, narrow enough that a real ranking change
#: trips it.
TOLERANCE = 0.02

#: Measured 2026-09-13 on the platform-only questions (n=8): GraphRAG recall@8
#: 0.535 against the legacy scorer's 0.669, a deficit of 0.134. The legacy
#: scorer is tuned on these exact 87 edges, so this is the one column where it
#: is expected to lead. The gate asserts the deficit stays inside this budget —
#: a real regression still trips it — rather than pretending the gap is not
#: there. Raising this number is a deliberate act; lowering it is progress.
PLATFORM_RECALL_GAP = 0.15

#: Same measurement for MRR: 0.418 against 0.729, a deficit of 0.311. MRR is
#: the harsher column because the legacy scorer's flat integers happen to put
#: the answer first more often, which is what a hand-tuned table buys you.
PLATFORM_MRR_GAP = 0.35


def load_fixture() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def platform_relations_path() -> Path | None:
    for directory in (RUNTIME_DIR, BASELINE_DIR):
        candidate = directory / "relations.csv"
        if candidate.exists():
            return candidate
    return None


def signature(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("source") or ""),
        str(row.get("relation") or ""),
        str(row.get("target") or ""),
    )


def recall_at_k(gold: list[list[str]], retrieved: list[tuple[str, str, str]], k: int = K) -> float:
    if not gold:
        return float("nan")
    wanted = {tuple(item) for item in gold}
    got = set(retrieved[:k])
    return len(wanted & got) / len(wanted)


def reciprocal_rank(gold: list[list[str]], retrieved: list[tuple[str, str, str]], k: int = K) -> float:
    if not gold:
        return float("nan")
    wanted = {tuple(item) for item in gold}
    for position, item in enumerate(retrieved[:k], start=1):
        if item in wanted:
            return 1.0 / position
    return 0.0


def link_recall(gold_entities: list[str], seeds: list[dict[str, Any]]) -> float:
    if not gold_entities:
        return float("nan")
    linked = {str(seed.get("name") or "").casefold() for seed in seeds}
    hit = sum(1 for name in gold_entities if name.casefold() in linked)
    return hit / len(gold_entities)


def chain_hit(chains: list[list[str]], retrieved: list[tuple[str, str, str]]) -> float:
    """Share of gold chains whose every consecutive pair was retrieved.

    A chain is the thing the path search exists to produce and the flat
    relation list cannot express, so it gets its own measure rather than being
    inferred from recall.
    """
    if not chains:
        return float("nan")
    edges = {(left, right) for left, _relation, right in retrieved}
    edges |= {(right, left) for left, _relation, right in retrieved}
    hits = 0
    for chain in chains:
        pairs = list(itertools.pairwise(chain))
        if pairs and all(pair in edges for pair in pairs):
            hits += 1
    return hits / len(chains)


def mean(values: list[float]) -> float:
    usable = [value for value in values if not math.isnan(value)]
    return statistics.fmean(usable) if usable else float("nan")


@pytest.fixture(autouse=True)
def zero_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any model call an exception.

    The evaluation runs the deterministic renderer, so a passing run *is* the
    proof that answering costs exactly zero LLM calls beyond the one the
    endpoint already made. A fixture that merely counted calls could pass while
    a stray summariser fired.
    """
    from backend.app.services import kg_llm

    def explode(*_args: Any, **_kwargs: Any) -> str:
        raise AssertionError("GraphRAG made an LLM call during evaluation")

    monkeypatch.setattr(kg_llm, "call_llm", explode)
    monkeypatch.setattr(kg_llm, "is_llm_configured", lambda: False)


class FixtureSelfCheckTest(unittest.TestCase):
    """Keeps the fixture honest as the graphs move underneath it.

    A gold relation that no longer exists in its source file would quietly turn
    a retrieval miss into an unanswerable question, and the recall numbers would
    drift *up* while the system got worse. This is the test that stops that.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.items = load_fixture()

    def test_every_item_is_well_formed(self) -> None:
        seen: set[str] = set()
        for item in self.items:
            self.assertNotIn(item["id"], seen, f"duplicate id {item['id']}")
            seen.add(item["id"])
            self.assertTrue(item["question"].strip())
            self.assertTrue(item["mode_expected"], item["id"])
            self.assertIn(item["sources"], ([], ["platform"], ["inherited"], ["platform", "inherited"]))

    def test_gold_relations_exist_in_their_source(self) -> None:
        import pandas as pd

        platform_path = platform_relations_path()
        self.assertIsNotNone(platform_path, "platform relations.csv not found")
        platform = {
            signature(row)
            for row in legacy.load_relations(platform_path)
        }

        frame = pd.read_parquet(INHERITED_PARQUET, columns=["source", "target"])
        inherited = {(str(a), "", str(b)) for a, b in zip(frame["source"], frame["target"])}

        checked = 0
        for item in self.items:
            for gold in item["gold_relations"]:
                key = tuple(gold)
                checked += 1
                if key[1] == "":
                    self.assertIn(key, inherited, f"{item['id']}: {key} not in the parquet")
                else:
                    self.assertIn(key, platform, f"{item['id']}: {key} not in relations.csv")
        self.assertGreater(checked, 0)

    def test_refusal_items_carry_no_gold(self) -> None:
        for item in self.items:
            if item["mode_expected"] == ["none"]:
                self.assertEqual(item["gold_relations"], [], item["id"])
                self.assertEqual(item["sources"], [], item["id"])

    def test_inherited_gold_uses_no_relation_label(self) -> None:
        """The parquet has no relation-type column: its ``description`` *is* the
        relation. A gold entry inventing a label would be describing an edge
        that does not exist."""
        for item in self.items:
            for gold in item["gold_relations"]:
                if item["sources"] == ["inherited"]:
                    self.assertEqual(gold[1], "", f"{item['id']}: {gold}")


class GraphRagEvaluationTest(unittest.TestCase):
    """The measured comparison. Run with ``-s`` to read the tables."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.items = load_fixture()
        cls.config = GraphRagConfig.from_env()
        cls.platform_path = platform_relations_path()
        cls.rows: list[dict[str, Any]] = []

        for item in cls.items:
            result = search(
                item["question"],
                config=cls.config,
                runtime_dir=RUNTIME_DIR,
                baseline_dir=BASELINE_DIR,
                project_root=REPO_ROOT,
                use_llm=False,
            )
            new = [signature(row) for row in result["matched_relations"]]
            old = [
                signature(row)
                for row in legacy.retrieve_graph_context(item["question"], cls.platform_path, top_k=K)
            ]
            cls.rows.append(
                {
                    "item": item,
                    "result": result,
                    "new": new,
                    "old": old,
                    "new_recall": recall_at_k(item["gold_relations"], new),
                    "old_recall": recall_at_k(item["gold_relations"], old),
                    "new_mrr": reciprocal_rank(item["gold_relations"], new),
                    "old_mrr": reciprocal_rank(item["gold_relations"], old),
                    "link_recall": link_recall(item["gold_entities"], result["seed_entities"]),
                    "chain": chain_hit(item["gold_chains"], new),
                }
            )
        cls._print_report()

    # -- reporting ---------------------------------------------------------

    @classmethod
    def _print_report(cls) -> None:
        print("\n" + "=" * 96)
        print("GraphRAG vs legacy scorer — same fixture, same repository data")
        print("=" * 96)
        header = f"{'id':<5}{'mode':<8}{'seeds':>6}{'links':>7}{'paths':>7}{'新R@8':>8}{'旧R@8':>8}{'新MRR':>8}{'旧MRR':>8}  question"
        print(header)
        print("-" * 96)
        for row in rows_ordered(cls.rows):
            item = row["item"]
            stats = row["result"]["stats"]
            print(
                f"{item['id']:<5}{row['result']['mode']:<8}{stats['seed_count']:>6}"
                f"{fmt(row['link_recall']):>7}{stats['path_count']:>7}"
                f"{fmt(row['new_recall']):>8}{fmt(row['old_recall']):>8}"
                f"{fmt(row['new_mrr']):>8}{fmt(row['old_mrr']):>8}  {item['question']}"
            )

        print("-" * 96)
        for label, rows in cls._grouped():
            new_r = mean([r["new_recall"] for r in rows])
            old_r = mean([r["old_recall"] for r in rows])
            new_m = mean([r["new_mrr"] for r in rows])
            old_m = mean([r["old_mrr"] for r in rows])
            print(
                f"{label:<22}n={len(rows):<4}"
                f"  recall@8 {fmt(new_r)} vs {fmt(old_r)}"
                f"   MRR {fmt(new_m)} vs {fmt(old_m)}"
            )

        print("-" * 96)
        accuracy = mean(
            [1.0 if row["result"]["mode"] in row["item"]["mode_expected"] else 0.0 for row in cls.rows]
        )
        refusals = [row for row in cls.rows if row["item"]["mode_expected"] == ["none"]]
        refusal_accuracy = mean(
            [
                1.0
                if row["result"]["mode"] == "none" and not row["result"]["matched_relations"]
                else 0.0
                for row in refusals
            ]
        )
        grounded = mean([row["result"]["stats"]["groundedness"] for row in cls.rows])
        validity = mean([row["result"]["stats"]["citation_validity"] for row in cls.rows])
        llm_calls = sum(1 for row in cls.rows if row["result"]["stats"]["llm_called"])
        print(
            f"routing accuracy {fmt(accuracy)}   refusal accuracy {fmt(refusal_accuracy)}"
            f"   groundedness {fmt(grounded)}   citation validity {fmt(validity)}"
            f"   LLM calls during evaluation: {llm_calls}"
        )
        print("=" * 96 + "\n")

    @classmethod
    def _grouped(cls) -> list[tuple[str, list[dict[str, Any]]]]:
        platform_only = [
            row for row in cls.rows if row["item"]["sources"] == ["platform"] and row["item"]["gold_relations"]
        ]
        inherited_only = [
            row for row in cls.rows if row["item"]["sources"] == ["inherited"] and row["item"]["gold_relations"]
        ]
        cross = [row for row in cls.rows if row["item"]["sources"] == ["platform", "inherited"]]
        scored = [row for row in cls.rows if row["item"]["gold_relations"]]
        return [
            ("platform only", platform_only),
            ("inherited only", inherited_only),
            ("cross-source", cross),
            ("all gold-bearing", scored),
        ]

    # -- gates -------------------------------------------------------------

    def test_no_llm_calls_during_retrieval(self) -> None:
        """The cost claim, mechanically: ``zero_llm_calls`` would have raised."""
        for row in self.rows:
            self.assertFalse(row["result"]["stats"]["llm_called"], row["item"]["id"])

    def test_aggregate_recall_does_not_regress(self) -> None:
        scored = [row for row in self.rows if row["item"]["gold_relations"]]
        new = mean([row["new_recall"] for row in scored])
        old = mean([row["old_recall"] for row in scored])
        self.assertGreaterEqual(new, old - TOLERANCE, f"recall@8 {new:.4f} vs legacy {old:.4f}")

    def test_aggregate_mrr_does_not_regress(self) -> None:
        scored = [row for row in self.rows if row["item"]["gold_relations"]]
        new = mean([row["new_mrr"] for row in scored])
        old = mean([row["old_mrr"] for row in scored])
        self.assertGreaterEqual(new, old - TOLERANCE, f"MRR {new:.4f} vs legacy {old:.4f}")

    def test_platform_retrieval_regression_stays_within_budget(self) -> None:
        """The honest one, and the only gate that permits a regression.

        The legacy scorer was hand-tuned on exactly this 87-edge graph and the
        fixture's platform questions were written by reading those same edges,
        so this is its home turf — GraphRAG is *not* expected to win here. What
        the gate buys is that the deficit is bounded and measured: if ranking
        changes make the platform column worse than the budget below, it fails,
        and the printed table shows by how much. Closing this gap is worth
        doing (a relation-word-insensitive ranker should eventually beat a
        hardcoded table), but not by tuning against eight questions.
        """
        rows = [row for row in self.rows if row["item"]["sources"] == ["platform"] and row["item"]["gold_relations"]]
        self.assertTrue(rows)
        new = mean([row["new_recall"] for row in rows])
        old = mean([row["old_recall"] for row in rows])
        self.assertGreaterEqual(
            new, old - PLATFORM_RECALL_GAP, f"platform recall@8 {new:.4f} vs legacy {old:.4f}"
        )
        new_mrr = mean([row["new_mrr"] for row in rows])
        old_mrr = mean([row["old_mrr"] for row in rows])
        self.assertGreaterEqual(
            new_mrr, old_mrr - PLATFORM_MRR_GAP, f"platform MRR {new_mrr:.4f} vs legacy {old_mrr:.4f}"
        )

    def test_legacy_scorer_cannot_reach_the_inherited_graph(self) -> None:
        """Documents the structural gap rather than assuming it.

        Worth stating precisely, because the convenient version of this claim —
        "the old path returns nothing for inherited questions" — is false.
        ``score_relation`` still fires on keyword overlap with the *platform*
        rows, so it returns three to eight confident-looking Chinese relations
        that do not answer the question. Returning the wrong graph is worse than
        returning nothing, and that is the honest framing of what changed.
        """
        platform = {
            signature(row) for row in legacy.load_relations(self.platform_path)
        }
        rows = [row for row in self.rows if row["item"]["sources"] == ["inherited"]]
        self.assertTrue(rows)
        for row in rows:
            for item in row["old"]:
                self.assertIn(item, platform, f"{row['item']['id']}: {item} is not a platform relation")
            self.assertEqual(row["old_recall"], 0.0, row["item"]["id"])

    def test_routing_matches_the_expected_band(self) -> None:
        wrong = [
            (row["item"]["id"], row["result"]["mode"], row["item"]["mode_expected"])
            for row in self.rows
            if row["result"]["mode"] not in row["item"]["mode_expected"]
        ]
        self.assertEqual(wrong, [])

    def test_refusals_are_clean(self) -> None:
        for row in self.rows:
            item = row["item"]
            if item["mode_expected"] != ["none"]:
                continue
            result = row["result"]
            self.assertEqual(result["mode"], "none", item["id"])
            self.assertEqual(result["matched_relations"], [], item["id"])
            self.assertEqual(result["paths"], [], item["id"])
            self.assertFalse(result["stats"]["degraded"], f"{item['id']}: a refusal is not a malfunction")

    def test_inherited_questions_are_answered_from_the_inherited_source(self) -> None:
        for row in self.rows:
            item = row["item"]
            if item["sources"] != ["inherited"]:
                continue
            self.assertTrue(row["new"], item["id"])
            source_ids = {
                seed["source_id"] for seed in row["result"]["seed_entities"]
            }
            self.assertIn("inherited", source_ids, item["id"])

    def test_cross_source_question_hears_from_both_graphs(self) -> None:
        rows = [row for row in self.rows if row["item"]["sources"] == ["platform", "inherited"]]
        self.assertTrue(rows)
        for row in rows:
            cited = {
                citation.get("source_id")
                for citation in row["result"]["citations"]
                if citation.get("source_id")
            }
            self.assertIn("platform", cited, row["item"]["id"])
            self.assertIn("inherited", cited, row["item"]["id"])

    def test_entity_linking_is_measured_not_assumed(self) -> None:
        """Reported, gated loosely: a name in the question that the linker
        cannot reach is a gap in ``BILINGUAL``, and the fix is a lexicon entry
        rather than a ranking change."""
        rows = [row for row in self.rows if row["item"]["gold_entities"]]
        self.assertGreaterEqual(mean([row["link_recall"] for row in rows]), 0.5)

    def test_answers_are_grounded_in_the_cited_materials(self) -> None:
        for row in self.rows:
            if row["item"]["mode_expected"] == ["none"]:
                continue
            stats = row["result"]["stats"]
            self.assertEqual(stats["hallucinated_markers"], [], row["item"]["id"])
            self.assertGreaterEqual(stats["citation_validity"], 0.99, row["item"]["id"])


class TestLlmPath:
    """The branch the deterministic renderer cannot exercise.

    ``groundedness`` is 1.0 by construction on the fallback path — every block
    it writes carries a marker — so its discriminating power only exists here,
    where the prose comes from a model and can be under-cited or invent a
    source. Both failure modes are injected deliberately.

    A plain class rather than a ``TestCase``: it needs the ``monkeypatch``
    fixture, and ``unittest``'s ``_callTestMethod`` cannot inject fixtures. So
    the assertions here are bare ``assert`` statements, not ``self.assert*``.
    """

    def _search_with_model(self, monkeypatch: pytest.MonkeyPatch, payload: str) -> dict[str, Any]:
        from backend.app.services import kg_llm

        monkeypatch.setattr(kg_llm, "is_llm_configured", lambda: True)
        monkeypatch.setattr(kg_llm, "call_llm", lambda *_a, **_k: payload)
        return search(
            "风如何影响水体浊度？",
            runtime_dir=RUNTIME_DIR,
            baseline_dir=BASELINE_DIR,
            project_root=REPO_ROOT,
            use_llm=True,
        )

    def test_under_cited_answer_scores_below_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = json.dumps(
            {
                "answer": "风速增加会导致底泥再悬浮，从而提高浊度[关系1]。这一机制在浅水湖泊中尤其显著。",
                "used_citations": ["关系1"],
                "insufficient": False,
            },
            ensure_ascii=False,
        )
        result = self._search_with_model(monkeypatch, payload)
        assert result["stats"]["llm_called"]
        # The second sentence asserts a mechanism with no marker on it. That is
        # the whole point: parsing the reply into JSON is what makes the
        # uncited sentence countable at all.
        assert result["stats"]["groundedness"] < 1.0
        assert result["stats"]["citation_validity"] == 1.0

    def test_fabricated_marker_is_caught_and_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = json.dumps(
            {
                "answer": "风速影响浊度[关系1]。沉积物再悬浮也起关键作用[关系99]。",
                "used_citations": ["关系1", "关系99"],
                "insufficient": False,
            },
            ensure_ascii=False,
        )
        result = self._search_with_model(monkeypatch, payload)
        assert result["stats"]["hallucinated_markers"] == ["[关系99]"]
        assert result["stats"]["citation_validity"] < 1.0
        assert "[关系99]" not in result["answer"]

    def test_unparseable_reply_falls_back_without_calling_it_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = self._search_with_model(monkeypatch, "抱歉，我无法回答。")
        # The model *was* called, so ``llm_called`` is true and the answer is the
        # rendering of the materials, not a refusal. ``degraded`` is true because
        # the reply could not be parsed into the contract — that is a reduced
        # mode, and it is reported as one rather than raised.
        assert result["stats"]["llm_called"]
        assert result["stats"]["degraded"]
        assert "关系1" in result["answer"]


def rows_ordered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fixture order, which groups platform, inherited, cross, refusals."""
    return rows


def fmt(value: float) -> str:
    return "  —  " if math.isnan(value) else f"{value:.3f}"
