"""Shared harness for API tests that stub the global auth guard.

The app's RBAC dependency (:func:`require_permission`) reads the resolved user
from ``request.state.actor_user``, which the real ``auth_guard`` sets after
validating the bearer token. A test that wants to exercise the *routes* rather
than the auth path still has to populate that state — otherwise every
permission-gated route answers 401. ``admin_auth_guard`` is a drop-in override
that does exactly that: it stamps an admin user so permission checks pass,
leaving the route's own behaviour as the thing under test.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import Request


def _admin_user() -> SimpleNamespace:
    return SimpleNamespace(role="admin", is_active=True)


async def admin_auth_guard(request: Request) -> None:
    """Populate ``request.state.actor_user`` as an admin, bypassing the token."""
    request.state.actor_user = _admin_user()
