"""Reports as governed business objects (review item 21).

Before this, ``/report/export`` rendered a file and handed back a download URL —
a report was a file, not a thing. It had no author, no reviewer, no approval
gate, no version, and no record of *which run* it described.

A :class:`ReportService` makes a report a first-class record that moves through
``draft → pending_review → approved/rejected → archived``. Generation is only
allowed once a report is approved, and at that moment the report's manifest
(the provenance of the run it describes) is locked into the record, so the file
and its metadata can never drift apart.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.config import Settings
from backend.app.domain.codes import ErrorCode, ReportStatus
from backend.app.services.report_builder import write_report
from backend.app.services.state_store import REPORTS_TABLE, SqliteStateStore
from backend.app.services.upload_guard import UploadRejected

ID_LENGTH = 12

#: Which report states may follow which.
REPORT_TRANSITIONS: dict[str, set[str]] = {
    ReportStatus.DRAFT: {ReportStatus.PENDING_REVIEW, ReportStatus.ARCHIVED},
    ReportStatus.PENDING_REVIEW: {ReportStatus.APPROVED, ReportStatus.REJECTED},
    ReportStatus.REJECTED: {ReportStatus.DRAFT, ReportStatus.ARCHIVED},
    ReportStatus.APPROVED: {ReportStatus.ARCHIVED},
    ReportStatus.ARCHIVED: set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ReportNotFound(KeyError):
    """No report with that id."""


class ReportService:
    def __init__(self, settings: Settings, store: SqliteStateStore) -> None:
        self.settings = settings
        self.store = store

    # -- creation ------------------------------------------------------------

    def create(
        self,
        *,
        title: str,
        author: str,
        case_id: str | None = None,
        project_name: str | None = None,
        format: str = "html",
        time_range_start: str | None = None,
        time_range_end: str | None = None,
        content_selection: list[str] | None = None,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        record = {
            "report_id": uuid4().hex[:ID_LENGTH],
            "created_at": timestamp,
            "updated_at": timestamp,
            "title": title.strip(),
            "project_name": project_name,
            "case_id": case_id,
            "status": str(ReportStatus.DRAFT),
            "author": author,
            "reviewer": None,
            "format": format,
            "time_range_start": time_range_start,
            "time_range_end": time_range_end,
            "content_selection": content_selection or [],
            "version": 1,
            "file_path": None,
            "filename": None,
            "download_url": None,
            "provenance": None,
            "reviewed_at": None,
            "review_comment": None,
            "archived_at": None,
        }
        return self.store.insert(REPORTS_TABLE, record)

    # -- reads ---------------------------------------------------------------

    def get(self, report_id: str) -> dict[str, Any]:
        report = self.store.get(REPORTS_TABLE, report_id)
        if report is None:
            raise ReportNotFound(report_id)
        return report

    def list(
        self,
        *,
        status: str | None = None,
        case_id: str | None = None,
        author: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if status:
            filters["status"] = status
        if case_id:
            filters["case_id"] = case_id
        if author:
            filters["author"] = author
        return self.store.list(REPORTS_TABLE, filters=filters or None, limit=limit)

    def update(self, report_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        report = self.get(report_id)
        if str(report.get("status")) not in {str(ReportStatus.DRAFT), str(ReportStatus.REJECTED)}:
            raise UploadRejected(
                ErrorCode.INVALID_STATE_TRANSITION,
                "Only a draft or rejected report may be edited.",
            )
        return self.store.update(
            REPORTS_TABLE, report_id, {**updates, "updated_at": utc_now()}
        )

    # -- review gate ---------------------------------------------------------

    def submit(self, report_id: str) -> dict[str, Any]:
        return self._transition(report_id, str(ReportStatus.PENDING_REVIEW))

    def review(self, report_id: str, approve: bool, reviewer: str, comment: str | None) -> dict[str, Any]:
        to_stage = str(ReportStatus.APPROVED if approve else ReportStatus.REJECTED)
        report = self.get(report_id)
        if str(report.get("status")) != str(ReportStatus.PENDING_REVIEW):
            raise UploadRejected(
                ErrorCode.INVALID_STATE_TRANSITION,
                "Only a pending-review report may be reviewed.",
            )
        return self.store.update(
            REPORTS_TABLE,
            report_id,
            {
                "status": to_stage,
                "reviewer": reviewer,
                "reviewed_at": utc_now(),
                "review_comment": comment,
                "updated_at": utc_now(),
            },
        )

    def _transition(self, report_id: str, to_stage: str) -> dict[str, Any]:
        report = self.get(report_id)
        current = str(report.get("status", ReportStatus.DRAFT))
        if to_stage not in REPORT_TRANSITIONS.get(current, set()):
            raise UploadRejected(
                ErrorCode.INVALID_STATE_TRANSITION,
                f"Cannot move report from {current} to {to_stage}.",
            )
        return self.store.update(
            REPORTS_TABLE, report_id, {"status": to_stage, "updated_at": utc_now()}
        )

    # -- generation ----------------------------------------------------------

    def generate(self, report_id: str, repository: Any, provenance: dict[str, Any]) -> dict[str, Any]:
        """Render the approved report and lock its manifest into the record.

        ``repository`` is the scoped :class:`ArtifactRepository` resolved by the
        route; passing it in keeps this service free of routing concerns.
        """
        report = self.get(report_id)
        if str(report.get("status")) != str(ReportStatus.APPROVED):
            raise UploadRejected(
                ErrorCode.REPORT_NOT_APPROVED,
                "A report must be approved before it can be generated.",
            )
        export_format = str(report.get("format") or "html")
        path = write_report(repository, self.settings.report_root, export_format=export_format)  # type: ignore[arg-type]
        version = int(report.get("version") or 1) + 1
        return self.store.update(
            REPORTS_TABLE,
            report_id,
            {
                "version": version,
                "file_path": str(path),
                "filename": path.name,
                "download_url": f"/api/v1/report/files/{path.name}",
                "provenance": provenance,
                "generated_at": utc_now(),
                "updated_at": utc_now(),
            },
        )

    # -- lifecycle -----------------------------------------------------------

    def archive(self, report_id: str, actor: str) -> dict[str, Any]:
        return self._transition(report_id, str(ReportStatus.ARCHIVED))

    def delete(self, report_id: str, actor: str) -> dict[str, Any]:
        report = self.get(report_id)
        if str(report.get("status")) in {str(ReportStatus.PENDING_REVIEW), str(ReportStatus.APPROVED)}:
            raise UploadRejected(
                ErrorCode.INVALID_STATE_TRANSITION,
                "A report under review or approved cannot be deleted; archive it instead.",
            )
        self.store.delete(REPORTS_TABLE, report_id)
        return {"report_id": report_id, "deleted": True, "deleted_by": actor}

    def summary(self) -> dict[str, Any]:
        reports = self.store.list(REPORTS_TABLE)
        by_status: dict[str, int] = {}
        for report in reports:
            status = str(report.get("status", ReportStatus.DRAFT))
            by_status[status] = by_status.get(status, 0) + 1
        return {
            "total": len(reports),
            "by_status": by_status,
            "pending_review": by_status.get(str(ReportStatus.PENDING_REVIEW), 0),
        }

    # -- retention -----------------------------------------------------------

    def purge_expired(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Delete archived reports past the retention window (review item 26).

        Only ``archived`` reports are ever purged — a draft, an in-review report,
        or an approved one whose file is still being cited is never touched.
        """
        retention_days = int(self.settings.report_retention_days)
        if retention_days <= 0:
            return {"scanned": 0, "purged": 0, "retention_days": retention_days, "skipped": "retention_disabled"}
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
        archived = self.store.list(
            REPORTS_TABLE, filters={"status": str(ReportStatus.ARCHIVED)}
        )
        expired: list[str] = []
        for report in archived:
            archived_at = report.get("archived_at")
            if not archived_at:
                continue
            try:
                parsed = datetime.fromisoformat(str(archived_at).replace("Z", "+00:00"))
                if parsed < cutoff:
                    expired.append(str(report["report_id"]))
            except ValueError:
                continue
        for report_id in expired:
            self.store.delete(REPORTS_TABLE, report_id)
        return {"scanned": len(archived), "purged": len(expired), "retention_days": retention_days}
