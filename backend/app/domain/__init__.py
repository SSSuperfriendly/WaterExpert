"""Domain vocabulary shared by every service layer.

Everything the API returns as a *state* or *category* is defined here as a
stable machine code. The frontend localizes those codes; it must never render a
backend prose string directly (see ``docs/reviews/2026-08-28-project-review.md``
item 22).
"""

from backend.app.domain.codes import (
    CaseStatus,
    DatasetStatus,
    ErrorCode,
    EventStatus,
    FailureCategory,
    IngestionStage,
    JobStatus,
    ModelStage,
    QualityGrade,
    ReportStatus,
    Severity,
)
from backend.app.domain.roles import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    permissions_for_role,
    role_has_permission,
)

__all__ = [
    "ROLE_PERMISSIONS",
    "CaseStatus",
    "DatasetStatus",
    "ErrorCode",
    "EventStatus",
    "FailureCategory",
    "IngestionStage",
    "JobStatus",
    "ModelStage",
    "Permission",
    "QualityGrade",
    "ReportStatus",
    "Role",
    "Severity",
    "permissions_for_role",
    "role_has_permission",
]
