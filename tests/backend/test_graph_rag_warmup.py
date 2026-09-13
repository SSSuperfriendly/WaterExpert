"""Priming the retrieval index at startup — and the three ways it must not hurt.

A warmup is an optimisation, and an optimisation that can delay or prevent
startup is a deoptimisation. These tests pin the three properties that keep it
one: it does not block the lifespan, it does not raise when the graph is
unreadable, and it can be switched off.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from backend.app import main
from backend.app.services.kg_service import KnowledgeGraphService


def _service() -> KnowledgeGraphService:
    """An instance without ``__init__``.

    ``warm_graph_rag`` only reaches ``self.build_agent_knowledge_context``, which
    each test patches on the class. A ``MagicMock`` would answer that lookup
    itself and every assertion below would pass without exercising anything.
    """
    return KnowledgeGraphService.__new__(KnowledgeGraphService)


class WarmupTest(unittest.TestCase):
    def test_the_service_offers_a_warmup_that_builds_a_context(self) -> None:
        with mock.patch.object(
            KnowledgeGraphService, "build_agent_knowledge_context", return_value={}
        ) as build:
            attempted = KnowledgeGraphService.warm_graph_rag(_service())
        self.assertTrue(attempted)
        build.assert_called_once()

    def test_a_broken_graph_is_logged_and_swallowed(self) -> None:
        """A graph that will not index must not stop the service from starting.

        The agent routes already degrade to the curated dictionary when
        retrieval fails; refusing to boot would turn a degraded answer into an
        outage.
        """
        with mock.patch.object(
            KnowledgeGraphService,
            "build_agent_knowledge_context",
            side_effect=RuntimeError("parquet is unreadable"),
        ):
            attempted = KnowledgeGraphService.warm_graph_rag(_service())
        self.assertTrue(attempted)

    def test_it_can_be_switched_off(self) -> None:
        with (
            mock.patch.dict("os.environ", {"WATEREXPERT_GRAPH_RAG_WARMUP": "off"}),
            mock.patch.object(
                KnowledgeGraphService, "build_agent_knowledge_context"
            ) as build,
        ):
            attempted = KnowledgeGraphService.warm_graph_rag(_service())
        self.assertFalse(attempted)
        build.assert_not_called()


class _FakeConnection:
    async def run_sync(self, _fn) -> None:
        return None


class _FakeBegin:
    async def __aenter__(self) -> _FakeConnection:
        return _FakeConnection()

    async def __aexit__(self, *_exc) -> bool:
        return False


async def _noop_seed() -> None:
    return None


class WarmupSchedulingTest(unittest.IsolatedAsyncioTestCase):
    """The scheduling half: off the startup path, and actually kept alive."""

    async def test_scheduling_does_not_wait_for_the_index(self) -> None:
        """``/healthz`` must answer before the index is built, not after."""
        started: list[str] = []

        def _warmup() -> bool:
            started.append("entered")
            return True

        with mock.patch.object(main.kg_service, "warm_graph_rag", _warmup):
            main._schedule_graph_rag_warmup()
            # The call is scheduled, not awaited: control returns here with the
            # worker thread none the wiser.
            self.assertEqual(started, [])
            for _ in range(20):
                if started:
                    break
                await asyncio.sleep(0.01)
        self.assertEqual(started, ["entered"])

    async def test_the_lifespan_schedules_the_warmup(self) -> None:
        """The scheduling above is unreachable unless ``lifespan`` calls it.

        Every test here passes if that one line is deleted, so the wiring needs
        its own assertion. The database and the demo user are stubbed: this is
        about the call site, not about starting a real app.
        """
        scheduled: list[str] = []
        with (
            mock.patch.object(main, "engine") as engine,
            mock.patch.object(main, "seed_demo_user", _noop_seed),
            mock.patch.object(
                main,
                "_schedule_graph_rag_warmup",
                lambda: scheduled.append("scheduled"),
            ),
        ):
            engine.begin.return_value = _FakeBegin()
            async with main.lifespan(main.app):
                pass
        self.assertEqual(scheduled, ["scheduled"])

    async def test_the_task_is_kept_referenced_until_it_finishes(self) -> None:
        """An unreferenced task can be collected mid-flight; the warmup then never lands."""
        with mock.patch.object(main.kg_service, "warm_graph_rag", return_value=True):
            main._schedule_graph_rag_warmup()
            self.assertEqual(len(main._warmup_tasks), 1)
            await asyncio.gather(*list(main._warmup_tasks))
            # The done-callback drops it, so the set does not grow across restarts.
            await asyncio.sleep(0)
            self.assertEqual(len(main._warmup_tasks), 0)

    async def test_a_failing_warmup_does_not_reach_the_event_loop(self) -> None:
        """An exception inside the task would otherwise be reported as unhandled."""
        with mock.patch.object(
            main.kg_service, "warm_graph_rag", side_effect=RuntimeError("unreadable")
        ):
            main._schedule_graph_rag_warmup()
            tasks = list(main._warmup_tasks)
            results = await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], RuntimeError)


if __name__ == "__main__":
    unittest.main()
