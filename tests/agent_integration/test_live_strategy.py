"""The platform's evidence, consumed by the running agent, end to end.

Everything else in the suite stops at the wire: the payload tests check what
the platform *sends*, and the agent's unit tests check what it does with a
hand-written context. Neither crosses, and the seam between them is where the
two defects that shipped this month both lived — a `knowledge_context` that no
caller ever requested, and checkpoints that `load_state_dict` rejected on every
agent so that ``inference_source`` was ``fallback_rules`` on every request
while ``/api/health`` said ``ready``.

So this test does the whole thing: build the real context from the repository's
graphs, POST it to the live agent, and read back what the agents actually did
with it. It skips when the agent is not running, because the agent is a separate
service with its own virtualenv and a backend-only test run has no way to start
it — a skip is the honest outcome there, and the assertions are the ones a
developer wants the moment they do start it.
"""

from __future__ import annotations

import json
import os
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from backend.app.config import Settings
from backend.app.services.kg_service import KnowledgeGraphService

REPO_ROOT = Path(__file__).resolve().parents[2]

AGENT_ROOT = os.environ.get("WATEREXPERT_AGENT_URL", "http://127.0.0.1:8001/api")

SCENARIO = "s2_internal_release"

STATE = {"date": "2025-10-31", "turbidity": 41.0, "flow_rate": 3.2, "rainfall_3d": 1.0}

#: A strategy run is one LLM call plus six agents; the poll budget has to be
#: longer than the job, not equal to it.
POLL_ATTEMPTS = 60
POLL_INTERVAL_SECONDS = 1.0


def make_settings() -> Settings:
    return Settings(
        app_name="test",
        project_root=REPO_ROOT,
        runtime_root=REPO_ROOT,
        frontend_root=REPO_ROOT / "frontend" / "out",
        report_root=REPO_ROOT / "var" / "reports",
        state_root=REPO_ROOT / "var" / "state",
    )


def agent_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{AGENT_ROOT}/health", timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def call(path: str, payload: dict | None = None, timeout: float = 20.0) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{AGENT_ROOT}{path}",
        data=data,
        headers={"content-type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


@unittest.skipUnless(agent_reachable(), f"agent not running at {AGENT_ROOT}")
class LiveStrategyConsumesGraphEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        context = KnowledgeGraphService(make_settings()).build_agent_knowledge_context(
            SCENARIO, {key: value for key, value in STATE.items() if key != "date"}
        )
        created = call(
            "/strategy",
            {
                "scenario": SCENARIO,
                "state": STATE,
                "episodes": 1,
                "backend": "api",
                "knowledge_context": context,
            },
        )
        job_id = created["job_id"]

        payload: dict = {}
        for _ in range(POLL_ATTEMPTS):
            payload = call(f"/strategy/{job_id}")
            if payload.get("status") in ("completed", "failed"):
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        cls.context = context
        cls.job = payload
        # The agent answers with the job's fields at the top level; the platform
        # route nests the same object under ``result``. Accept either, so this
        # test is about the agent rather than about which door it came through.
        cls.result = payload.get("result") or payload

    def test_the_job_finished(self) -> None:
        self.assertEqual(self.job.get("status"), "completed", self.job.get("error"))

    def test_the_knowledge_base_knows_it_was_grounded(self) -> None:
        """``+GraphRAG`` is the agent saying it read the evidence it was sent.

        The bare name means it fell back to its curated dictionary, which is
        what every strategy request did while ``with_knowledge`` was opt-in and
        nothing opted in.
        """
        kb = self.result["agent_traces"]["kb"]["output"]
        self.assertEqual(kb["source"], "KnowledgeBaseAgent+GraphRAG", kb)
        self.assertTrue(kb["grounded"])
        self.assertTrue(kb["citations"])

    def test_candidates_from_both_graphs_reach_the_recommendations(self) -> None:
        """The same both-graphs property as the payload test, one hop later."""
        kb = self.result["agent_traces"]["kb"]["output"]
        labels = {
            item["source_label"]
            for item in kb["recommendations"]
            if item.get("origin") == "graph"
        }
        self.assertIn("基线图谱", labels)
        self.assertIn("继承图谱（合作方 GraphRAG）", labels)

    def test_the_case_backed_techniques_carry_their_case(self) -> None:
        kb = self.result["agent_traces"]["kb"]["output"]
        curated = [item for item in kb["recommendations"] if item.get("origin") == "scenario"]
        self.assertTrue(curated)
        for item in curated:
            with self.subTest(technique=item["technique"]):
                # A dose with no unit is not a dose. The old dictionary returned
                # a bare 0.5 and 0.7 against no case at all.
                self.assertIsInstance(item["intensity"], (int, float))
                self.assertTrue(item["intensity_unit"])
                self.assertTrue(item["case_id"])
                self.assertTrue(item["reference"])

    def test_the_diagnosis_says_whether_a_model_produced_it(self) -> None:
        """The one field that separates a prediction from a rule of thumb.

        Asserted as "the field is present and truthy" rather than as
        ``checkpoint``: which of the two ran is a fact about this machine's
        checkpoints, and the test is about the platform reporting it. A run
        that degraded must say so here — that is the whole assertion.
        """
        for agent in ("mscim", "cmfbe"):
            with self.subTest(agent=agent):
                trace = self.result["agent_traces"][agent]
                self.assertIn("inference_source", trace["output"], trace["output"])

    def test_the_run_is_not_silently_rule_based(self) -> None:
        """Checkpoints are on disk, so the models must be the ones answering.

        This is the assertion the 2026-09-08 swap needed and did not have. It
        is deliberately strict: if a checkpoint stops loading, the right outcome
        is a red test, not a green one with a footnote.
        """
        for agent in ("mscim", "cmfbe"):
            with self.subTest(agent=agent):
                trace = self.result["agent_traces"][agent]["output"]
                self.assertEqual(
                    trace.get("inference_source"),
                    "checkpoint",
                    trace.get("checkpoint_error") or trace.get("error"),
                )


if __name__ == "__main__":
    unittest.main()
