"""The analysis case: the object that ties one conclusion to its evidence.

Review items 4 and 5 found that a result had no identity. A user picked a date,
ran a job, and read numbers off several pages — with nothing recording which
data, which config and which model produced them, and nothing stopping a page
from quietly serving *last* run's integrated artifacts instead.

A :class:`Case` fixes that by binding, in one record:

* the dataset versions that went in, and their quality verdict,
* the config snapshot and its hash,
* the job that ran and the model version it produced,
* the artifacts that came out, and
* whether those artifacts are still current for the inputs.

Every result endpoint resolves through a case, so "which run is this number
from?" always has an answer.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.config import Settings
from backend.app.domain.codes import CaseStatus, ErrorCode, JobStatus
from backend.app.services.dataset_service import DatasetNotFound, DatasetService
from backend.app.services.state_store import CASES_TABLE, SqliteStateStore
from backend.app.services.upload_guard import UploadRejected

ID_LENGTH = 12
#: Terminal job states that leave a case unable to serve results.
FAILED_JOB_STATUSES = {
    str(JobStatus.FAILED),
    str(JobStatus.CANCELLED),
    str(JobStatus.TIMEOUT),
    str(JobStatus.ORPHANED),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class CaseNotFound(KeyError):
    """No case with that id."""


def config_hash(config_path: Path) -> str:
    """Content hash of the config a run used.

    Two cases with the same hash ran the same configuration; a case whose hash
    no longer matches its config file has had that file changed underneath it.
    """
    try:
        payload = config_path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(payload).hexdigest()[:16]


class CaseService:
    def __init__(
        self,
        settings: Settings,
        store: SqliteStateStore,
        datasets: DatasetService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.datasets = datasets

    # -- creation ------------------------------------------------------------

    def create_case(
        self,
        *,
        title: str,
        owner: str,
        station_code: str | None = None,
        target_date: str | None = None,
        dataset_version_ids: list[str] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Open a case over a set of dataset versions.

        The versions are gated here rather than at run time: a case may only be
        built on data that passed the quality chain (review item 9), so an
        unusable input is refused while the user is still looking at the form.
        """
        version_ids = list(dataset_version_ids or [])
        versions = [self._assert_usable_version(version_id) for version_id in version_ids]
        coverage_start, coverage_end = (
            self.datasets.coverage_window(version_ids) if version_ids else (None, None)
        )

        timestamp = utc_now()
        case = {
            "case_id": uuid4().hex[:ID_LENGTH],
            "created_at": timestamp,
            "updated_at": timestamp,
            "title": title.strip() or "Untitled case",
            "description": description,
            "owner": owner,
            "status": str(CaseStatus.DRAFT),
            "station_code": station_code,
            "target_date": target_date,
            "input_dataset_versions": version_ids,
            "data_quality": self._quality_digest(versions),
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
            "job_id": None,
            "run_id": None,
            "config_hash": None,
            "model_version": None,
            "report_ids": [],
            "artifacts_generated_at": None,
        }
        created = self.store.insert(CASES_TABLE, case)
        if version_ids:
            self.datasets.record_case_usage(version_ids, str(case["case_id"]))
        return created

    def _assert_usable_version(self, version_id: str) -> dict[str, Any]:
        try:
            return self.datasets.assert_modelable(version_id)
        except DatasetNotFound as exc:
            raise UploadRejected(
                ErrorCode.NOT_FOUND, f"Dataset version {version_id} does not exist."
            ) from exc

    @staticmethod
    def _quality_digest(versions: list[dict[str, Any]]) -> dict[str, Any]:
        """The quality verdict the case was opened against.

        Stored rather than looked up later so the case records what was true at
        creation; a dataset re-ingested afterwards makes the case stale rather
        than silently changing its provenance.
        """
        if not versions:
            return {"version_count": 0, "grades": [], "modelable_rows": 0}
        return {
            "version_count": len(versions),
            "grades": sorted({str(version.get("quality_grade", "")) for version in versions}),
            "modelable_rows": sum(
                int(version.get("modelable_rows") or 0) for version in versions
            ),
            "versions": [
                {
                    "version_id": version["version_id"],
                    "dataset_id": version.get("dataset_id"),
                    "version": version.get("version"),
                    "quality_grade": version.get("quality_grade"),
                    "coverage_start": version.get("coverage_start"),
                    "coverage_end": version.get("coverage_end"),
                }
                for version in versions
            ],
        }

    # -- reads ---------------------------------------------------------------

    def get_case(self, case_id: str) -> dict[str, Any]:
        case = self.store.get(CASES_TABLE, case_id)
        if case is None:
            raise CaseNotFound(case_id)
        return case

    def list_cases(
        self,
        *,
        owner: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if owner:
            filters["owner"] = owner
        if status:
            filters["status"] = status
        return self.store.list(CASES_TABLE, filters=filters or None, limit=limit)

    def case_for_job(self, job_id: str) -> dict[str, Any] | None:
        """The case a job belongs to, if any.

        Lets a legacy ``?job_id=`` read still carry full case provenance instead
        of degrading to an anonymous result.
        """
        matches = self.store.list(CASES_TABLE, filters={"job_id": job_id}, limit=1)
        return matches[0] if matches else None

    def update_case(self, case_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        self.get_case(case_id)
        return self.store.update(
            CASES_TABLE, case_id, {**updates, "updated_at": utc_now()}
        )

    # -- run binding ---------------------------------------------------------

    def attach_job(self, case_id: str, job: dict[str, Any]) -> dict[str, Any]:
        """Bind a launched job to the case and record what identifies its run."""
        config_snapshot = job.get("config_snapshot_path")
        return self.update_case(
            case_id,
            {
                "job_id": job.get("job_id"),
                "run_id": job.get("job_id"),
                "status": str(CaseStatus.RUNNING),
                "model_version": job.get("model_name"),
                "config_snapshot_path": config_snapshot,
                "config_hash": config_hash(Path(str(config_snapshot))) if config_snapshot else None,
                "requested_parameters": job.get("requested_parameters"),
            },
        )

    def sync_from_job(self, case_id: str, job: dict[str, Any]) -> dict[str, Any]:
        """Reflect a job's current state onto its case."""
        case = self.get_case(case_id)
        job_status = str(job.get("status", ""))

        if job_status == str(JobStatus.COMPLETED):
            updates = {
                "status": str(CaseStatus.READY),
                "artifacts_generated_at": job.get("finished_at") or utc_now(),
                "artifacts": job.get("artifacts"),
                "effective_parameters": job.get("effective_parameters"),
            }
        elif job_status in FAILED_JOB_STATUSES:
            updates = {
                "status": str(CaseStatus.FAILED),
                "failure_message": job.get("message"),
            }
        elif job_status == str(JobStatus.RUNNING):
            updates = {"status": str(CaseStatus.RUNNING)}
        else:
            return case

        return self.update_case(case_id, updates)

    # -- freshness -----------------------------------------------------------

    def is_stale(self, case: dict[str, Any]) -> tuple[bool, str | None]:
        """Whether a case's artifacts predate the inputs they claim to explain.

        Review item 5: a page must be able to say "these results are older than
        the data behind them" instead of presenting them as current. Returns the
        verdict and, when stale, the reason.
        """
        generated_at = case.get("artifacts_generated_at")
        if not generated_at:
            return False, None

        for version_id in case.get("input_dataset_versions") or []:
            try:
                version = self.datasets.get_version(str(version_id))
            except DatasetNotFound:
                return True, "input_dataset_deleted"
            if str(version.get("created_at", "")) > str(generated_at):
                return True, "input_dataset_newer"

        snapshot_path = case.get("config_snapshot_path")
        recorded_hash = case.get("config_hash")
        if snapshot_path and recorded_hash:
            if config_hash(Path(str(snapshot_path))) != recorded_hash:
                return True, "config_changed"

        return False, None

    def case_view(self, case_id: str) -> dict[str, Any]:
        """A case plus the freshness verdict every result page needs."""
        case = self.get_case(case_id)
        stale, reason = self.is_stale(case)
        if stale and case.get("status") == str(CaseStatus.READY):
            case = self.update_case(case_id, {"status": str(CaseStatus.STALE)})
        return {**case, "is_stale": stale, "stale_reason": reason}

    def assert_readable(self, case_id: str) -> dict[str, Any]:
        """The gate every result endpoint runs before serving artifacts."""
        case = self.case_view(case_id)
        status = str(case.get("status"))
        if status in {str(CaseStatus.DRAFT), str(CaseStatus.RUNNING)}:
            raise UploadRejected(
                ErrorCode.CASE_NOT_READY,
                f"Case {case_id} is {status}; its results are not available yet.",
            )
        if status == str(CaseStatus.FAILED):
            raise UploadRejected(
                ErrorCode.CASE_NOT_READY,
                f"Case {case_id} failed: {case.get('failure_message') or 'no artifacts produced'}.",
            )
        return case

    # -- provenance ----------------------------------------------------------

    def provenance(self, case_id: str) -> dict[str, Any]:
        """The version stamp attached to every artifact response.

        Review item 5 asked for `run_id`, `generated_at`, `model_version` and
        `config_hash` on each payload so two pages can be compared for
        agreement instead of assumed to agree.
        """
        case = self.case_view(case_id)
        return {
            "case_id": case["case_id"],
            "run_id": case.get("run_id"),
            "job_id": case.get("job_id"),
            "generated_at": case.get("artifacts_generated_at"),
            "model_version": case.get("model_version"),
            "config_hash": case.get("config_hash"),
            "is_stale": case.get("is_stale", False),
            "stale_reason": case.get("stale_reason"),
            "scope": "case",
        }

    @staticmethod
    def integrated_provenance() -> dict[str, Any]:
        """The stamp for the shared, non-case-scoped research artifacts.

        These are the repository's checked-in outputs. They are readable only
        when a caller explicitly asks for ``scope=integrated``, and they say so
        loudly, because attributing them to a user's run was the original defect.
        """
        return {
            "case_id": None,
            "run_id": None,
            "generated_at": None,
            "model_version": None,
            "config_hash": None,
            "is_stale": False,
            "stale_reason": None,
            "scope": "integrated",
            "is_integrated_default": True,
        }

    # -- lifecycle -----------------------------------------------------------

    def archive_case(self, case_id: str, actor: str) -> dict[str, Any]:
        return self.update_case(
            case_id,
            {"status": str(CaseStatus.ARCHIVED), "archived_by": actor, "archived_at": utc_now()},
        )

    def delete_case(self, case_id: str, actor: str) -> dict[str, Any]:
        """Remove a case. Refused while reports still cite it."""
        case = self.get_case(case_id)
        report_ids = case.get("report_ids") or []
        if report_ids:
            raise UploadRejected(
                ErrorCode.INVALID_STATE_TRANSITION,
                f"Case {case_id} is cited by {len(report_ids)} report(s); "
                "archive it instead of deleting.",
            )
        self.store.delete(CASES_TABLE, case_id)
        return {"case_id": case_id, "deleted": True, "deleted_by": actor}

    def attach_report(self, case_id: str, report_id: str) -> dict[str, Any]:
        case = self.get_case(case_id)
        report_ids = list(case.get("report_ids") or [])
        if report_id not in report_ids:
            report_ids.append(report_id)
        return self.update_case(case_id, {"report_ids": report_ids})

    # -- operational summary -------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Counts the operational homepage needs (review item 12)."""
        cases = self.store.list(CASES_TABLE)
        by_status: dict[str, int] = {}
        stale = 0
        for case in cases:
            status = str(case.get("status", CaseStatus.DRAFT))
            by_status[status] = by_status.get(status, 0) + 1
            if self.is_stale(case)[0]:
                stale += 1
        return {
            "total": len(cases),
            "by_status": by_status,
            "stale_count": stale,
            "pending_count": by_status.get(str(CaseStatus.DRAFT), 0)
            + by_status.get(str(CaseStatus.RUNNING), 0),
        }
