"""Stable machine codes for every state and error the API can return.

Two rules follow from the 2026-08-28 review (item 22):

* The API returns a code from this module, never a localized sentence.
* The frontend maps the code through ``lib/i18n`` and owns the wording.

Codes are lowercase snake_case and are part of the API contract: renaming one is
a breaking change.
"""

from __future__ import annotations

from enum import Enum


class _Code(str, Enum):
    """String enum whose members serialize as their bare value."""

    def __str__(self) -> str:
        return str(self.value)


class IngestionStage(_Code):
    """The data-acceptance chain from review item 3.

    A dataset version advances one stage at a time and stops at the first stage
    that fails, so ``stage`` alone answers "where is this data stuck?".
    """

    UPLOADED = "uploaded"
    VALIDATED = "validated"
    MAPPED = "mapped"
    CLEANED = "cleaned"
    ALIGNED = "aligned"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


INGESTION_STAGE_ORDER: tuple[IngestionStage, ...] = (
    IngestionStage.UPLOADED,
    IngestionStage.VALIDATED,
    IngestionStage.MAPPED,
    IngestionStage.CLEANED,
    IngestionStage.ALIGNED,
    IngestionStage.ACCEPTED,
)


class DatasetStatus(_Code):
    """Lifecycle of a dataset version as an asset (review item 8)."""

    DRAFT = "draft"
    PROCESSING = "processing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    DELETED = "deleted"


class QualityGrade(_Code):
    """Overall data-quality grade. Only A and B are modelable by default."""

    A = "a"
    B = "b"
    C = "c"
    D = "d"


MODELABLE_GRADES: frozenset[QualityGrade] = frozenset({QualityGrade.A, QualityGrade.B})


class JobStatus(_Code):
    """Task-centre state machine from review item 10."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ORPHANED = "orphaned"


TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.CANCELLED,
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.TIMEOUT,
        JobStatus.ORPHANED,
    }
)

ACTIVE_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING}
)


class FailureCategory(_Code):
    """Why a job failed, so the task centre can say more than "failed"."""

    CONFIG_INVALID = "config_invalid"
    DATA_MISSING = "data_missing"
    DATA_QUALITY_REJECTED = "data_quality_rejected"
    DEPENDENCY_MISSING = "dependency_missing"
    ARTIFACT_INCOMPLETE = "artifact_incomplete"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PROCESS_CRASHED = "process_crashed"
    UNKNOWN = "unknown"


class CaseStatus(_Code):
    """Lifecycle of an analysis case (review item 4)."""

    DRAFT = "draft"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    STALE = "stale"
    ARCHIVED = "archived"


class ModelStage(_Code):
    """Model lifecycle from review item 11: 实验 → 候选 → 审核 → 发布 → 运行 → 退役."""

    EXPERIMENT = "experiment"
    CANDIDATE = "candidate"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    RETIRED = "retired"


class ReportStatus(_Code):
    """Report as a business object with a review gate (review item 21)."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Severity(_Code):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventStatus(_Code):
    """事件发现 → 分派 → 确认 → 处置 → 复核 → 关闭 → 复盘 (review item 27)."""

    OPEN = "open"
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    HANDLING = "handling"
    REVIEWING = "reviewing"
    CLOSED = "closed"
    FALSE_POSITIVE = "false_positive"


class ErrorCode(_Code):
    """Stable error codes returned in ``{"code": ..., "detail": ...}``.

    ``detail`` stays English and is for operators and logs; the frontend renders
    ``code`` through its own catalogue.
    """

    # auth / access
    NOT_AUTHENTICATED = "not_authenticated"
    INVALID_CREDENTIALS = "invalid_credentials"
    TOKEN_INVALID = "token_invalid"
    ACCOUNT_INACTIVE = "account_inactive"
    PERMISSION_DENIED = "permission_denied"
    ALREADY_REGISTERED = "already_registered"

    # request shape
    VALIDATION_FAILED = "validation_failed"
    UNSUPPORTED_FORMAT = "unsupported_format"
    FILE_TOO_LARGE = "file_too_large"
    CONTENT_TYPE_REJECTED = "content_type_rejected"
    PATH_NOT_ALLOWED = "path_not_allowed"
    COMPRESSION_RATIO_REJECTED = "compression_ratio_rejected"

    # domain
    NOT_FOUND = "not_found"
    CASE_REQUIRED = "case_required"
    CASE_NOT_READY = "case_not_ready"
    RESULT_STALE = "result_stale"
    DATASET_NOT_MODELABLE = "dataset_not_modelable"
    DATE_RANGE_OUT_OF_COVERAGE = "date_range_out_of_coverage"
    MODEL_NOT_PUBLISHED = "model_not_published"
    UNSUPPORTED_COMBINATION = "unsupported_combination"
    JOB_NOT_CANCELLABLE = "job_not_cancellable"
    QUOTA_EXCEEDED = "quota_exceeded"
    REPORT_NOT_APPROVED = "report_not_approved"
    INVALID_STATE_TRANSITION = "invalid_state_transition"

    # infrastructure
    ARTIFACT_UNAVAILABLE = "artifact_unavailable"
    ARTIFACT_UNREADABLE = "artifact_unreadable"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    INTERNAL_ERROR = "internal_error"
