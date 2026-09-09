"""Personal centre: self-service account management under ``/api/v1/users/me``.

These endpoints replace the stock ``fastapi-users`` users router, which is no
longer mounted. The stock router exposed a PATCH that accepted ``role`` — any
reviewer could hand themselves ``admin`` (self-escalation), and it allowed a
user to delete their own account out from under its ownership records. Self-
service here is deliberately narrow and symmetric:

* ``GET    /me``            — the caller's own profile (the only user record the
  caller may read; there is no user directory).
* ``PATCH  /me/profile``    — change display-only fields (no password needed;
  nothing here changes the sign-in identity or privileges).
* ``PATCH  /me/username``   — change the login name (re-auth with the current
  password, so a stolen session token alone cannot hijack the account).
* ``PATCH  /me/email``      — change the contact email (same re-auth rule).
* ``POST   /me/password``   — change the password (same re-auth rule).

Role is immutable through self-service by design. Everything that changes the
sign-in identity or the credential re-verifies the current password because the
bearer token lives in the browser's sessionStorage; a token theft must not be
enough to lock the owner out. Display-name edits are the one thing that do not
re-auth, mirroring what a profile page should tolerate.

All handlers resolve the caller from ``request.state.actor_user`` (set by the
global ``auth_guard`` in ``main.py`` after it validates the token) and run their
writes through the request-scoped ``UserManager`` session, so an identity that
authenticated a moment ago is reloaded fresh before it is mutated.
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select

from backend.app.domain.codes import ErrorCode
from backend.app.models import User
from backend.app.schemas import (
    EmailUpdateRequest,
    PasswordChangeRequest,
    ProfileRead,
    ProfileUpdateRequest,
    SetPasswordRequest,
    UsernameUpdateRequest,
)
from backend.app.users import (
    UserManager,
    decode_reauth_token,
    get_user_manager,
)

router = APIRouter(tags=["users"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _refuse(code: ErrorCode, detail: str, status_code: int) -> HTTPException:
    """Mirror ``main.error_response`` without importing the app (no circulars)."""
    return HTTPException(
        status_code=status_code, detail={"code": str(code), "detail": detail}
    )


def _actor(request: Request) -> User:
    """The authenticated caller, stamped on the request by the global guard."""
    user = getattr(request.state, "actor_user", None)
    if user is None:
        # The global auth guard runs first and rejects anonymous traffic;
        # reaching a handler without a user is a mis-wired route, fail closed.
        raise _refuse(ErrorCode.NOT_AUTHENTICATED, "Not authenticated.", 401)
    return user


def _provider_names(user: User) -> list[str]:
    """Linked identity providers (``github`` etc.), never the account ids."""
    try:
        accounts = list(getattr(user, "oauth_accounts", None) or [])
    except Exception:
        # A detached user whose relationship was expired: not worth re-loading
        # just for the provider list; treat as unlinked.
        return []
    return sorted({account.oauth_name for account in accounts if account.oauth_name})


def _profile(user: User, providers: list[str]) -> ProfileRead:
    return ProfileRead(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        # A usable password is exactly a non-empty hash: OAuth-created accounts
        # store "" until the holder sets one (see users.oauth_callback).
        has_password=bool(user.hashed_password),
        oauth_providers=providers,
    )


async def _reload(manager: UserManager, user_id: uuid.UUID) -> User:
    """Reload the caller inside the manager's session before mutating."""
    user = await manager.user_db.session.get(User, user_id)
    if user is None:
        raise _refuse(ErrorCode.NOT_FOUND, "Account no longer exists.", 404)
    return user


def _verify_current_password(manager: UserManager, user: User, password: str) -> None:
    """Re-verify the caller knows the current password before an identity edit.

    Uses the freshly reloaded row's hash so a concurrent change is respected.
    """
    if not user.hashed_password:
        # OAuth-only account: there is nothing to verify against, so the caller
        # is not "wrong" — it has not set a password yet. A distinct code lets
        # the UI send them to the set-password flow instead of implying a typo.
        raise _refuse(
            ErrorCode.PASSWORD_NOT_SET,
            "This account has no usable password; set one first.",
            400,
        )
    verified, _ = manager.password_helper.verify_and_update(password, user.hashed_password)
    if not verified:
        raise _refuse(
            ErrorCode.CURRENT_PASSWORD_INCORRECT,
            "Current password is incorrect.",
            400,
        )


@router.get("/me", response_model=ProfileRead)
async def read_me(request: Request) -> ProfileRead:
    actor = _actor(request)
    return _profile(actor, _provider_names(actor))


@router.patch("/me/profile", response_model=ProfileRead)
async def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    manager: UserManager = Depends(get_user_manager),
) -> ProfileRead:
    actor = _actor(request)
    fresh = await _reload(manager, actor.id)
    providers = _provider_names(fresh)
    display_name = (payload.display_name or "").strip()
    if display_name and display_name != fresh.display_name:
        fresh = await manager.user_db.update(fresh, {"display_name": display_name})
    return _profile(fresh, providers)


@router.patch("/me/username", response_model=ProfileRead)
async def update_username(
    payload: UsernameUpdateRequest,
    request: Request,
    manager: UserManager = Depends(get_user_manager),
) -> ProfileRead:
    actor = _actor(request)
    fresh = await _reload(manager, actor.id)
    providers = _provider_names(fresh)
    _verify_current_password(manager, fresh, payload.current_password)
    new_username = payload.username.strip()
    if new_username == fresh.username:
        return _profile(fresh, providers)  # idempotent no-op
    if await _username_taken(manager, new_username, fresh.id):
        raise _refuse(
            ErrorCode.USERNAME_TAKEN, f"Username {new_username!r} is taken.", 409
        )
    updates: dict[str, object] = {"username": new_username}
    if fresh.display_name == fresh.username:
        # Registered accounts default display_name to the login name; follow
        # the rename so the sidebar and headers do not go stale.
        updates["display_name"] = new_username
    fresh = await manager.user_db.update(fresh, updates)
    return _profile(fresh, providers)


@router.patch("/me/email", response_model=ProfileRead)
async def update_email(
    payload: EmailUpdateRequest,
    request: Request,
    manager: UserManager = Depends(get_user_manager),
) -> ProfileRead:
    actor = _actor(request)
    fresh = await _reload(manager, actor.id)
    providers = _provider_names(fresh)
    _verify_current_password(manager, fresh, payload.current_password)
    new_email = payload.email.strip()
    if not _EMAIL_RE.fullmatch(new_email):
        raise _refuse(ErrorCode.VALIDATION_FAILED, "Invalid email address.", 400)
    if new_email.lower() == fresh.email.lower():
        return _profile(fresh, providers)  # idempotent no-op
    if await _email_taken(manager, new_email, fresh.id):
        raise _refuse(ErrorCode.EMAIL_TAKEN, "That email is already in use.", 409)
    fresh = await manager.user_db.update(fresh, {"email": new_email})
    return _profile(fresh, providers)


@router.post("/me/password", response_model=ProfileRead)
async def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    manager: UserManager = Depends(get_user_manager),
) -> ProfileRead:
    actor = _actor(request)
    fresh = await _reload(manager, actor.id)
    providers = _provider_names(fresh)
    _verify_current_password(manager, fresh, payload.current_password)
    if payload.new_password == payload.current_password:
        raise _refuse(
            ErrorCode.VALIDATION_FAILED,
            "The new password must differ from the current one.",
            400,
        )
    new_hash = manager.password_helper.hash(payload.new_password)
    fresh = await manager.user_db.update(fresh, {"hashed_password": new_hash})
    return _profile(fresh, providers)


@router.post("/me/set-password", response_model=ProfileRead)
async def set_password(
    payload: SetPasswordRequest,
    request: Request,
    manager: UserManager = Depends(get_user_manager),
) -> ProfileRead:
    """Set a first password on an OAuth-only account (no current password).

    Identity is proven by the session *plus* a fresh GitHub re-auth: the caller
    must present the short-lived capability the OAuth callback mints after the
    signed-in holder re-authorizes GitHub. Without it, a stolen session token
    would be enough to put an attacker-chosen password on the account.
    """
    actor = _actor(request)
    fresh = await _reload(manager, actor.id)
    providers = _provider_names(fresh)
    if fresh.hashed_password:
        raise _refuse(
            ErrorCode.PASSWORD_ALREADY_SET,
            "This account already has a password; change it instead.",
            400,
        )
    if payload.new_password != payload.confirm_password:
        raise _refuse(ErrorCode.VALIDATION_FAILED, "Passwords do not match.", 400)
    claims = decode_reauth_token(payload.reauth_token)
    if (
        claims is None
        or claims.get("pur") != "set_password"
        or claims.get("sub") != str(fresh.id)
    ):
        raise _refuse(
            ErrorCode.PASSWORD_REAUTH_REQUIRED,
            "Re-authorize with GitHub to confirm identity before setting a password.",
            400,
        )
    new_hash = manager.password_helper.hash(payload.new_password)
    fresh = await manager.user_db.update(fresh, {"hashed_password": new_hash})
    return _profile(fresh, providers)


async def _username_taken(
    manager: UserManager, username: str, exclude_id: uuid.UUID
) -> bool:
    statement = select(User.id).where(User.username == username)
    existing = (await manager.user_db.session.execute(statement)).scalar_one_or_none()
    return existing is not None and existing != exclude_id


async def _email_taken(manager: UserManager, email: str, exclude_id: uuid.UUID) -> bool:
    statement = select(User.id).where(func.lower(User.email) == email.lower())
    existing = (await manager.user_db.session.execute(statement)).scalar_one_or_none()
    return existing is not None and existing != exclude_id
