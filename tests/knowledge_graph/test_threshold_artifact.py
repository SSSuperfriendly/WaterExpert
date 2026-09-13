"""The threshold graph and the summary it is exported from have to agree.

Two files carry the same ten critical levels: ``cmfbe_threshold_summary.csv``,
which is the fit that produced them, and
``mechanism_parameter_threshold_kg.json``, which is the reading copy — the one
``artifact_repository.thresholds()`` serves to the console and the one the
agent is now sent.

Nothing checked that they matched, and they are written by different steps of
the same pipeline. A half-completed export leaves the file that humans read and
the file the agent screens against stating different levels, and every consumer
would be individually consistent and collectively wrong. That is the shape of
the defect that put this file here: the agent's own snapshot of the CSV had
drifted, four levels of ten, so a rule-based run warned about 3-day rain at
35.9 mm while the graph said 49.1.

Read both, compare them, and fail with the feature name rather than a diff.
"""

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SUMMARY_PATH = REPO_ROOT / "outputs" / "thresholds" / "cmfbe_threshold_summary.csv"
GRAPH_PATH = REPO_ROOT / "outputs" / "thresholds" / "mechanism_parameter_threshold_kg.json"


def summary_levels() -> dict[str, dict[str, str]]:
    """The rows the export treats as thresholds: ``status == "ok"``.

    The same filter ``agent_exports._build_threshold_lookup`` applies. A feature
    whose split did not converge carries an empty ``threshold`` and a status
    saying so, and is excluded rather than read as zero.
    """
    with SUMMARY_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {
        str(row["feature"]): row
        for row in rows
        if str(row.get("status") or "") == "ok" and str(row.get("threshold") or "").strip()
    }


class ThresholdArtifactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.levels = summary_levels()
        cls.graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        cls.nodes = {node["feature"]: node for node in cls.graph["threshold_nodes"]}

    def test_the_export_actually_produced_something(self) -> None:
        """Every assertion below holds vacuously over an empty export."""
        self.assertTrue(self.levels)
        self.assertTrue(self.nodes)

    def test_both_files_carry_the_same_features(self) -> None:
        self.assertEqual(sorted(self.nodes), sorted(self.levels))

    def test_every_level_matches_the_fit_it_came_from(self) -> None:
        for feature, row in self.levels.items():
            with self.subTest(feature=feature):
                node = self.nodes.get(feature)
                self.assertIsNotNone(node, f"{feature} is a threshold in the summary but not in the graph")
                self.assertAlmostEqual(
                    float(node["threshold"]),
                    float(row["threshold"]),
                    places=9,
                    msg=f"{feature}: graph says {node['threshold']}, the fit says {row['threshold']}",
                )

    def test_every_node_carries_the_unit_and_the_fit(self) -> None:
        """What the graph adds over the CSV is readability, not new numbers."""
        for feature, node in self.nodes.items():
            with self.subTest(feature=feature):
                self.assertTrue(node.get("unit"), node)
                self.assertTrue(node.get("agent_label"), node)
                self.assertIsNotNone(node.get("r2_gain"), node)
                self.assertIsNotNone(node.get("response_jump"), node)

    def test_the_graph_states_the_limits_of_its_own_claim(self) -> None:
        self.assertTrue(self.graph.get("scope"))
        self.assertTrue(self.graph.get("threshold_semantics"))
        self.assertTrue(self.graph.get("guardrails"))


if __name__ == "__main__":
    unittest.main()
