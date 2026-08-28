"""RBAC enforcement and audit logging.

Review items 6 and 7. The ``role`` column existed but nothing consulted it, and
there was no record of who did what. This module provides both:

* ``require_permission`` — a FastAPI dependency a route declares to say "only
  roles with this permission may call me". It runs *after* the global auth
  guard, so by the time it resolves a request there is always a valid user.
* ``AuditLogger`` — writes an ``audit_events`` row per privileged action with
  the actor, action, object, outcome, client IP and time.

Neither imports the FastAPI app, so both are testable in isolation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, Request

from backend.app.domain.codes import ErrorCode
from backend.app.domain.roles import Permission, parse_role, role_has_permission
from backend.app.services.state_store import AUDIT_EVENTS_TABLE, SqliteStateStore


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class PermissionDenied(ValueError):
    """The caller's role may not perform this action."""

    def __init__(self, permission: Permission, role: str) -> None:
        super().__init__(f"Role '{role}' lacks permission '{permission}'.")
        self.permission = permission
        self.role = role


class AuditLogger:
    """Append-only record of privileged actions (review item 7)."""

    def __init__(self, store: SqliteStateStore) -> None:
        self.store = store

    def record(
        self,
        *,
        actor: str,
        action: str,
        object_type: str,
        object_id: str | None = None,
        outcome: str = "success",
        detail: str | None = None,
        ip: str | None = None,
    ) -> dict[str, Any]:
        return self.store.insert(
            AUDIT_EVENTS_TABLE,
            {
                "audit_id": _audit_id(),
                "created_at": utc_now(),
                "actor": actor,
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
                "outcome": outcome,
                "detail": detail,
                "ip": ip,
            },
        )

    def list(
        self,
        *,
        actor: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if actor:
            filters["actor"] = actor
        if action:
            filters["action"] = action
        return self.store.list(AUDIT_EVENTS_TABLE, filters=filters or None, limit=limit)

    def recent_refusals(self, *, actor: str, within_seconds: int = 60) -> int:
        """Count of 401/403/404 responses this actor drew recently.

        Used to flag an access that keeps failing — a credential brute-force or a
        probing session (review item 7).
        """
        cutoff = datetime.now(timezone.utc).timestamp() - within_seconds
        total = 0
        for event in self.store.list(AUDIT_EVENTS_TABLE, filters={"actor": actor}):
            created = event.get("created_at")
            if not created:
                continue
            try:
                stamp = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            except ValueError:
                continue
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            if stamp.timestamp() < cutoff:
                continue
            if event.get("outcome") in {"denied", "not_found", "unauthorized"}:
                total += 1
        return total


def _audit_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


def _require_permission_dependency(
    permission: Permission,
):
    async def dependency(request: Request) -> None:
        user = getattr(request.state, "actor_user", None)
        if user is None:
            # The global auth guard runs first and rejects an anonymous request;
            # reaching here without a user is a mis-wired route, fail closed.
            from fastapi import HTTPException

            raise HTTPException(
                status_code=401,
                detail={"code": str(ErrorCode.NOT_AUTHENTICATED), "detail": "Not authenticated."},
            )
        role = parse_role(getattr(user, "role", None))
        if not role_has_permission(role, permission):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=403,
                detail={
                    "code": str(ErrorCode.PERMISSION_DENIED),
                    "detail": f"Role '{role}' lacks permission '{permission}'.",
                },
            )

    return dependency


def require_permission(permission: Permission):
    """Dependency factory: gate a route on a single permission.

    Returns a plain async callable so the route can declare it as ``Depends``::

        @app.post("/api/v1/models/publish")
        def publish(_: None = Depends(require_permission(Permission.MODEL_PUBLISH))): ...

    (Returning a ``Depends`` here would double-wrap it; FastAPI then sees a
    ``Depends`` object as the dependency callable and refuses to import.)
    """
    return _require_permission_dependency(permission)
