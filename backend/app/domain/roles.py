"""Role-based access control.

The 2026-08-28 review (item 6) found a ``role`` column that nothing enforced.
This module is the single source of truth for what each role may do; the
``require_permission`` dependency in ``backend.app.security`` is the only place
that should consult it.

Three roles, as the review specified:

* ``admin``    — 系统管理员: everything, including user management and model publishing.
* ``reviewer`` — 审核人员: reviews and approves reports, acknowledges events, edits
  thresholds. May run analyses but may not publish models or manage users.
* ``operator`` — 业务用户: day-to-day work — upload data, run cases, export reports.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    OPERATOR = "operator"

    def __str__(self) -> str:
        return str(self.value)


class Permission(str, Enum):
    """One entry per privileged action named in review item 6."""

    DATA_UPLOAD = "data:upload"
    DATA_DELETE = "data:delete"
    DATA_READ = "data:read"

    CASE_CREATE = "case:create"
    CASE_DELETE = "case:delete"
    JOB_START = "job:start"
    JOB_CANCEL = "job:cancel"

    MODEL_PUBLISH = "model:publish"
    MODEL_RETIRE = "model:retire"

    THRESHOLD_EDIT = "threshold:edit"

    REPORT_EXPORT = "report:export"
    REPORT_REVIEW = "report:review"
    REPORT_DELETE = "report:delete"

    KG_BUILD = "kg:build"

    EVENT_ASSIGN = "event:assign"
    EVENT_HANDLE = "event:handle"
    EVENT_CLOSE = "event:close"

    USER_MANAGE = "user:manage"
    AUDIT_READ = "audit:read"
    MAINTENANCE = "maintenance:run"

    def __str__(self) -> str:
        return str(self.value)


_OPERATOR_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.DATA_READ,
        Permission.DATA_UPLOAD,
        Permission.CASE_CREATE,
        Permission.JOB_START,
        Permission.JOB_CANCEL,
        Permission.REPORT_EXPORT,
        Permission.KG_BUILD,
        Permission.EVENT_HANDLE,
    }
)

_REVIEWER_PERMISSIONS: frozenset[Permission] = _OPERATOR_PERMISSIONS | frozenset(
    {
        Permission.DATA_DELETE,
        Permission.CASE_DELETE,
        Permission.THRESHOLD_EDIT,
        Permission.REPORT_REVIEW,
        Permission.EVENT_ASSIGN,
        Permission.EVENT_CLOSE,
        Permission.AUDIT_READ,
    }
)

_ADMIN_PERMISSIONS: frozenset[Permission] = frozenset(Permission)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OPERATOR: _OPERATOR_PERMISSIONS,
    Role.REVIEWER: _REVIEWER_PERMISSIONS,
    Role.ADMIN: _ADMIN_PERMISSIONS,
}

DEFAULT_ROLE = Role.OPERATOR


def parse_role(value: str | Role | None) -> Role:
    """Coerce a stored role string to a :class:`Role`, defaulting to operator.

    Unknown values degrade to the least-privileged role rather than raising, so
    a hand-edited or legacy database row can never widen access.
    """
    if isinstance(value, Role):
        return value
    try:
        return Role(str(value or "").strip().lower())
    except ValueError:
        return DEFAULT_ROLE


def permissions_for_role(role: str | Role | None) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[parse_role(role)]


def role_has_permission(role: str | Role | None, permission: Permission) -> bool:
    return permission in permissions_for_role(role)
