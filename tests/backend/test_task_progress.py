"""The task centre's derived view: progress, failure category, elapsed time.

Review item 10. Everything here is a pure function of a job record, so the
weighting and classification rules can be pinned without running a pipeline.
"""

from __future__ import annotations

import unittest

from backend.app.domain.codes import FailureCategory, JobStatus
from backend.app.services.task_progress import (
    classify_failure,
    estimated_remaining_seconds,
    progress_percent,
    task_view,
)


def _job(status: str, **overrides) -> dict:
    record: dict = {"job_id": "j", "status": status, "created_at": "2026-01-01T00:00:00Z"}
    record.update(overrides)
    return record


class ProgressTest(unittest.TestCase):
    def test_queued_is_zero(self) -> None:
        self.assertEqual(progress_percent(_job(str(JobStatus.QUEUED))), 0)

    def test_completed_is_pinned_to_100(self) -> None:
        self.assertEqual(progress_percent(_job(str(JobStatus.COMPLETED))), 100)

    def test_pipeline_stage_reports_more_than_zero_but_not_done(self) -> None:
        record = _job(str(JobStatus.RUNNING), stage="pipeline")
        percent = progress_percent(record)
        self.assertGreater(percent, 0)
        self.assertLess(percent, 100)

    def test_later_stages_report_more_progress_than_earlier(self) -> None:
        early = progress_percent(_job(str(JobStatus.RUNNING), stage="pipeline"))
        late = progress_percent(_job(str(JobStatus.RUNNING), stage="agent-context-export"))
        self.assertGreater(late, early)

    def test_failed_job_does_not_rewind_progress(self) -> None:
        record = _job(str(JobStatus.FAILED), stage="sobol-counterfactual")
        self.assertGreater(progress_percent(record), 0)

    def test_unknown_stage_is_not_a_crash(self) -> None:
        self.assertGreaterEqual(progress_percent(_job(str(JobStatus.RUNNING), stage="mystery")), 0)


class FailureClassificationTest(unittest.TestCase):
    def test_config_error_is_classified(self) -> None:
        record = _job(str(JobStatus.FAILED), message="Config file must decode to a mapping")
        self.assertEqual(classify_failure(record), str(FailureCategory.CONFIG_INVALID))

    def test_missing_module_is_a_dependency_problem(self) -> None:
        record = _job(str(JobStatus.FAILED), stderr_preview=["ModuleNotFoundError: No module named 'torch'"])
        self.assertEqual(classify_failure(record), str(FailureCategory.DEPENDENCY_MISSING))

    def test_incomplete_artifacts_are_distinguished(self) -> None:
        record = _job(str(JobStatus.FAILED), message="Job-scoped artifact chain is incomplete")
        self.assertEqual(classify_failure(record), str(FailureCategory.ARTIFACT_INCOMPLETE))

    def test_timeout_and_cancelled_map_directly(self) -> None:
        self.assertEqual(classify_failure(_job(str(JobStatus.TIMEOUT))), str(FailureCategory.TIMEOUT))
        self.assertEqual(classify_failure(_job(str(JobStatus.CANCELLED))), str(FailureCategory.CANCELLED))

    def test_orphaned_is_a_crash(self) -> None:
        self.assertEqual(classify_failure(_job(str(JobStatus.ORPHANED))), str(FailureCategory.PROCESS_CRASHED))

    def test_a_completed_job_has_no_failure_category(self) -> None:
        self.assertIsNone(classify_failure(_job(str(JobStatus.COMPLETED))))

    def test_unrecognised_failure_is_unknown_not_none(self) -> None:
        self.assertEqual(
            classify_failure(_job(str(JobStatus.FAILED), message="something else entirely")),
            str(FailureCategory.UNKNOWN),
        )


class ElapsedTest(unittest.TestCase):
    def test_a_fresh_run_has_no_remaining_estimate(self) -> None:
        # No started_at yet: the runner has been spawned but not reported in.
        record = _job(str(JobStatus.RUNNING), stage="pipeline", created_at=None)
        self.assertIsNone(estimated_remaining_seconds(record))

    def test_task_view_attaches_the_derived_fields(self) -> None:
        view = task_view(_job(str(JobStatus.QUEUED)))
        self.assertIn("progress", view)
        self.assertIn("stage_order", view)
        self.assertEqual(view["progress"], 0)


if __name__ == "__main__":
    unittest.main()
