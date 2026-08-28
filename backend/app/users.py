"""fastapi-users wiring: user manager, JWT authentication backend, and helpers.

This module replaces the previous demo-grade ``UserStore``/``AuthService`` pair
with the mature ``fastapi-users`` stack:

* ``UserManager`` — create / authenticate / reset-password / verify users.
* JWT ``AuthenticationBackend`` (Bearer transport) — signs and validates tokens.
* ``FastAPIUsers`` — factories for the reset-password, verify, users and OAuth
  routers mounted in ``main.py``.
* ``seed_demo_user`` — provisions the default demo account (hashed password) so
  the workbench remains usable before real users register.

Email delivery (password-reset and verification) uses a console transport: the
token is logged rather than sent over SMTP. Point ``on_after_*`` at a real
sender when SMTP credentials are available.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid

from fastapi import Depends
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users import exceptions as user_exceptions
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.jwt import decode_jwt
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from backend.app.config import get_settings
from backend.app.db import async_session_maker, get_async_session
from backend.app.models import OAuthAccount, User
from backend.app.schemas import UserCreate

logger = logging.getLogger(__name__)

_settings = get_settings()

JWT_AUDIENCE = ["fastapi-users:auth"]
JWT_LIFETIME_SECONDS = int(os.environ.get("WATEREXPERT_JWT_LIFETIME_SECONDS", "3600"))

DEMO_USERNAME = os.environ.get("WATEREXPERT_DEMO_USERNAME", "2510709")
DEMO_PASSWORD = os.environ.get("WATEREXPERT_DEMO_PASSWORD", "AI4S666")
DEMO_DISPLAY_NAME = os.environ.get("WATEREXPERT_DEMO_DISPLAY_NAME", "AI4S Demo User")
DEMO_ROLE = os.environ.get("WATEREXPERT_DEMO_ROLE", "reviewer")


def _load_jwt_secret() -> str:
    """Resolve the JWT signing secret from env, a persisted file, or generate one.

    A generated secret is persisted under ``state_root`` (gitignored) so issued
    tokens survive restarts, which is required for a non-demo deployment.
    """
    from_env = os.environ.get("WATEREXPERT_JWT_SECRET")
    if from_env:
        return from_env
    secret_path = _settings.state_root / "jwt_secret"
    if secret_path.exists():
        existing = secret_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    generated = secrets.token_urlsafe(48)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(generated, encoding="utf-8")
    return generated


SECRET = _load_jwt_secret()


def get_jwt_strategy() -> JWTStrategy:
    """Build the JWT strategy used both for issuing and validating tokens."""
    return JWTStrategy(secret=SECRET, lifetime_seconds=JWT_LIFETIME_SECONDS)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=BearerTransport(tokenUrl="/api/v1/auth/login"),
    get_strategy=get_jwt_strategy,
)


def demo_credentials() -> dict[str, str]:
    return {"username": DEMO_USERNAME, "password": DEMO_PASSWORD}


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
):
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """User manager with username support and console email transport."""

    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    # -- identity lookup -----------------------------------------------------

    async def get_by_username(self, username: str) -> User | None:
        statement = select(User).where(User.username == username.strip())
        result = await self.user_db.session.execute(statement)
        return result.scalar_one_or_none()

    async def authenticate_identifier(
        self, identifier: str, password: str
    ) -> User | None:
        """Authenticate by username (exact) or email (case-insensitive)."""
        identifier = (identifier or "").strip()
        if not identifier:
            return None
        user = await self.user_db.get_by_email(identifier)
        if user is None:
            user = await self.get_by_username(identifier)
        if user is None:
            # Hash anyway to blunt user-enumeration timing attacks.
            self.password_helper.hash(password)
            return None
        verified, updated_hash = self.password_helper.verify_and_update(
            password, user.hashed_password
        )
        if not verified:
            return None
        if updated_hash is not None:
            await self.user_db.update(user, {"hashed_password": updated_hash})
        return user

    # -- uniqueness ----------------------------------------------------------

    async def create(
        self,
        user_create: UserCreate,
        safe: bool = False,
        request=None,
    ) -> User:
        existing = await self.get_by_username(user_create.username)
        if existing is not None:
            raise user_exceptions.UserAlreadyExists()
        return await super().create(user_create, safe=safe, request=request)

    # -- OAuth account provisioning -----------------------------------------

    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: int | None = None,
        refresh_token: str | None = None,
        request=None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> User:
        """Replicate the base OAuth flow, adding username/display_name on create."""
        oauth_account_dict = {
            "oauth_name": oauth_name,
            "access_token": access_token,
            "account_id": account_id,
            "account_email": account_email,
            "expires_at": expires_at,
            "refresh_token": refresh_token,
        }
        try:
            user = await self.get_by_oauth_account(oauth_name, account_id)
        except user_exceptions.UserNotExists:
            try:
                user = await self.get_by_email(account_email)
                if not associate_by_email:
                    raise user_exceptions.UserAlreadyExists()
                user = await self.user_db.add_oauth_account(user, oauth_account_dict)
            except user_exceptions.UserNotExists:
                password = self.password_helper.generate()
                username = await self._unique_oauth_username(account_email, account_id)
                user_dict = {
                    "email": account_email,
                    "hashed_password": self.password_helper.hash(password),
                    "is_verified": is_verified_by_default,
                    "username": username,
                    "display_name": account_email.split("@", 1)[0],
                    "role": "reviewer",
                }
                user = await self.user_db.create(user_dict)
                user = await self.user_db.add_oauth_account(user, oauth_account_dict)
                await self.on_after_register(user, request)
        else:
            for existing_oauth_account in user.oauth_accounts:
                if (
                    existing_oauth_account.account_id == account_id
                    and existing_oauth_account.oauth_name == oauth_name
                ):
                    user = await self.user_db.update_oauth_account(
                        user, existing_oauth_account, oauth_account_dict
                    )
        return user

    async def _unique_oauth_username(self, account_email: str, account_id: str) -> str:
        base = (account_email.split("@", 1)[0] or "gh").lower()
        if await self.get_by_username(base) is None:
            return base
        suffix = account_id.replace("-", "")[:8]
        candidate = f"{base}_{suffix}"
        if await self.get_by_username(candidate) is None:
            return candidate
        return f"{base}_{account_id[:12]}"

    # -- email transport (console) ------------------------------------------

    async def on_after_register(self, user: User, request=None) -> None:
        logger.info("Registered user %s (%s)", user.username, user.email)

    async def on_after_forgot_password(
        self, user: User, token: str, request=None
    ) -> None:
        logger.info(
            "Password reset requested for %s. Token: %s "
            "(POST /api/v1/auth/reset-password with {token, password})",
            user.email,
            token,
        )

    async def on_after_request_verify(
        self, user: User, token: str, request=None
    ) -> None:
        logger.info(
            "Email verification requested for %s. Token: %s "
            "(POST /api/v1/auth/verify with {token})",
            user.email,
            token,
        )

    async def on_after_reset_password(self, user: User, request=None) -> None:
        logger.info("Password reset completed for %s", user.email)


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)


async def authenticate_token(token: str) -> User | None:
    """Validate a bearer JWT and return the active user, or ``None``.

    Used by the global API auth guard in ``main.py`` to protect the data
    endpoints without resolving FastAPI dependencies on public routes.
    """
    try:
        data = decode_jwt(token, SECRET, JWT_AUDIENCE)
        user_id = data.get("sub")
    except jwt.PyJWTError:
        return None
    if not user_id:
        return None
    try:
        parsed_id = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None
    async with async_session_maker() as session:
        user = await session.get(User, parsed_id)
    if user is None or not user.is_active:
        return None
    return user


async def seed_demo_user() -> None:
    """Provision the default demo account if it does not already exist."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.username == DEMO_USERNAME)
        )
        if result.scalar_one_or_none() is not None:
            return
        password_helper = PasswordHelper()
        demo_email = os.environ.get(
            "WATEREXPERT_DEMO_EMAIL", f"{DEMO_USERNAME}@example.com"
        )
        user = User(
            username=DEMO_USERNAME,
            email=demo_email,
            display_name=DEMO_DISPLAY_NAME,
            role=DEMO_ROLE,
            hashed_password=password_helper.hash(DEMO_PASSWORD),
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        logger.info("Seeded demo user %r", DEMO_USERNAME)
