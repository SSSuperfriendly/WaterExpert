"""Turning a job's raw state into something the task centre can show a person.

Review item 10 asked for three things a bare status string cannot give:

* a **progress percentage** that means something — the runner already writes the
  stage it is on, so the weights below convert that into a number rather than
  the usual spinner that sits at "running" for two hours;
* a **failure category**, so "failed" becomes "the config was invalid" or "the
  data was missing" — the difference between something the user can fix and
  something they should report;
* an **elapsed / remaining** estimate built from the same weights.

Everything here is a pure function of a job record, so it is testable without
launching a pipeline.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend.app.domain.codes import FailureCategory, JobStatus

#: Stage names as ``backend/app/tasks/job_runner.py`` writes them, with the share
#: of total runtime each accounts for. Training dominates by an order of
#: magnitude, so a naive "4 of 6 steps done = 66%" would be badly wrong; these
#: weights come from the step ordering in the runner and keep the bar honest.
STAGE_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("queued", 0.0),
    ("pipeline", 0.62),
    ("threshold-analysis", 0.10),
    ("threshold-knowledge-graph", 0.06),
    ("sobol-counterfactual", 0.14),
    ("agent-context-export", 0.05),
    ("artifact-validation", 0.03),
)

STAGE_ORDER: tuple[str, ...] = tuple(stage for stage, _ in STAGE_WEIGHTS)
_STAGE_INDEX: dict[str, int] = {stage: index for index, stage in enumerate(STAGE_ORDER)}
#: Progress reported while a stage is in flight — the stage has started, so its
#: own weight is credited at this fraction rather than all-or-nothing.
IN_FLIGHT_FRACTION = 0.5


def _cumulative_before(stage: str) -> float:
    index = _STAGE_INDEX.get(stage)
    if index is None:
        return 0.0
    return sum(weight for _, weight in STAGE_WEIGHTS[:index])


def progress_percent(record: dict[str, Any]) -> int:
    """How far along this job is, 0-100.

    A terminal job is pinned to its outcome (100 for completed, whatever it had
    reached for a failure) so the bar never rewinds.
    """
    status = str(record.get("status", ""))
    if status == str(JobStatus.COMPLETED):
        return 100
    if status == str(JobStatus.QUEUED):
        return 0

    stage = str(record.get("stage") or "")
    if not stage:
        # Running with no stage reported yet: the runner has been spawned but
        # has not written its first status file.
        return 1 if status == str(JobStatus.RUNNING) else 0

    weight = dict(STAGE_WEIGHTS).get(stage, 0.0)
    fraction = _cumulative_before(stage) + weight * IN_FLIGHT_FRACTION
    return max(0, min(99, round(fraction * 100)))


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def elapsed_seconds(record: dict[str, Any], *, now: datetime | None = None) -> int | None:
    """Wall-clock seconds this job has been running, or ran for."""
    started = _parse_timestamp(record.get("started_at") or record.get("created_at"))
    if started is None:
        return None
    finished = _parse_timestamp(record.get("finished_at"))
    end = finished or (now or datetime.now(timezone.utc))
    return max(0, int((end - started).total_seconds()))


def estimated_remaining_seconds(record: dict[str, Any], *, now: datetime | None = None) -> int | None:
    """A remaining-time estimate, or ``None`` when there is nothing to base one on.

    Deliberately returns ``None`` rather than a number early in a run: an
    estimate extrapolated from three seconds of elapsed time is a guess dressed
    up as information.
    """
    if str(record.get("status", "")) != str(JobStatus.RUNNING):
        return None
    elapsed = elapsed_seconds(record, now=now)
    percent = progress_percent(record)
    if elapsed is None or elapsed < 30 or percent < 5:
        return None
    total = elapsed / (percent / 100)
    return max(0, int(total - elapsed))


#: Signatures matched against a failed job's message and log tail, most specific
#: first. Each maps to the category that tells a user what to do next.
_FAILURE_SIGNATURES: tuple[tuple[re.Pattern[str], FailureCategory], ...] = (
    (re.compile(r"run scope|runscopeerror|no rows|empty dataset", re.I), FailureCategory.DATA_MISSING),
    (re.compile(r"config file (not found|must decode)|yaml|invalid config", re.I), FailureCategory.CONFIG_INVALID),
    (re.compile(r"quality|not modelable|rejected dataset", re.I), FailureCategory.DATA_QUALITY_REJECTED),
    (re.compile(r"artifact chain is incomplete|artifacts were missing", re.I), FailureCategory.ARTIFACT_INCOMPLETE),
    (re.compile(r"modulenotfound|importerror|no module named|command not found", re.I), FailureCategory.DEPENDENCY_MISSING),
    (re.compile(r"filenotfound|no such file or directory", re.I), FailureCategory.DATA_MISSING),
    (re.compile(r"cuda out of memory|killed|memoryerror|segmentation fault", re.I), FailureCategory.PROCESS_CRASHED),
)


def classify_failure(record: dict[str, Any]) -> str | None:
    """Why this job failed, in the vocabulary of :class:`FailureCategory`.

    Returns ``None`` for a job that has not failed, so the caller can attach the
    field unconditionally.
    """
    status = str(record.get("status", ""))
    if status == str(JobStatus.TIMEOUT):
        return str(FailureCategory.TIMEOUT)
    if status == str(JobStatus.CANCELLED):
        return str(FailureCategory.CANCELLED)
    if status == str(JobStatus.ORPHANED):
        return str(FailureCategory.PROCESS_CRASHED)
    if status != str(JobStatus.FAILED):
        return None

    haystack = " ".join(
        str(part)
        for part in (
            record.get("message"),
            record.get("error"),
            *(record.get("stderr_preview") or []),
        )
        if part
    )
    for pattern, category in _FAILURE_SIGNATURES:
        if pattern.search(haystack):
            return str(category)
    return str(FailureCategory.UNKNOWN)


def task_view(record: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """The job record plus everything the task centre renders from it."""
    view = {
        **record,
        "progress": progress_percent(record),
        "elapsed_seconds": elapsed_seconds(record, now=now),
        "estimated_remaining_seconds": estimated_remaining_seconds(record, now=now),
        "stage_order": list(STAGE_ORDER),
    }
    category = classify_failure(record)
    if category is not None:
        view["failure_category"] = category
    return view
