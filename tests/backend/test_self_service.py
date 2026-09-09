"""Personal centre (self-service account management) — API contract tests.

The routes under ``/api/v1/users/me`` are protected by the global ``auth_guard``
and run their writes through the request-scoped ``UserManager``. These tests
point both at a throwaway SQLite database (fresh engine per request, created
inside the TestClient's loop) and provision real users in it, so the guard
override stamps a real persisted user and the manager mutates the same rows the
way the app does in production. They also pin that the *stock* fastapi-users
users router is gone — a reviewer could previously PATCH their own ``role`` to
``admin`` through it.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from backend.app import main
from backend.app.db import Base
from backend.app.models import OAuthAccount, User
from backend.app.users import UserManager, issue_reauth_token

USER_A = "persona_a"
USER_B = "persona_b"
# A pure-GitHub (OAuth-created) account: no usable password until it sets one.
USER_GH = "persona_gh"
PASS_A = "Passw0rd-AA-1"
PASS_B = "Passw0rd-BB-1"
EMAIL_A = "persona_a@example.com"
EMAIL_B = "persona_b@example.com"
EMAIL_GH = "persona_gh@example.com"
GITHUB_ACCOUNT_ID = "gh-account-111"


def _hash(password: str) -> str:
    return PasswordHelper().hash(password)


def _run(coro):
    return asyncio.run(coro)


class SelfServiceApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_url = f"sqlite+aiosqlite:///{Path(self._tmp.name) / 'auth.sqlite3'}"

        async def _seed() -> None:
            engine = create_async_engine(self._db_url, connect_args={"timeout": 30})
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                maker = async_sessionmaker(engine, expire_on_commit=False)
                async with maker() as session:
                    for username, email, password in (
                        (USER_A, EMAIL_A, PASS_A),
                        (USER_B, EMAIL_B, PASS_B),
                    ):
                        session.add(
                            User(
                                username=username,
                                email=email,
                                display_name=username,
                                role="reviewer",
                                hashed_password=_hash(password),
                                is_active=True,
                                is_verified=True,
                                is_superuser=False,
                            )
                        )
                    # OAuth-created account: empty hash (no usable password yet).
                    session.add(
                        User(
                            username=USER_GH,
                            email=EMAIL_GH,
                            display_name=USER_GH,
                            role="reviewer",
                            hashed_password="",
                            is_active=True,
                            is_verified=True,
                            is_superuser=False,
                            oauth_accounts=[
                                OAuthAccount(
                                    oauth_name="github",
                                    access_token="stub-access-token",
                                    account_id=GITHUB_ACCOUNT_ID,
                                    account_email=EMAIL_GH,
                                )
                            ],
                        )
                    )
                    await session.commit()
                    result = await session.execute(
                        select(User)
                        .where(User.username == USER_A)
                        .options(selectinload(User.oauth_accounts))
                    )
                    self._user_a = result.scalar_one()
                    gh = await session.execute(
                        select(User)
                        .where(User.username == USER_GH)
                        .options(selectinload(User.oauth_accounts))
                    )
                    self._user_gh = gh.scalar_one()
            finally:
                await engine.dispose()

        _run(_seed())

        self._existing_overrides = dict(main.app.dependency_overrides)
        self._actor = self._user_a

        async def _manager_override():
            # Built per request inside the TestClient loop: async SQLAlchemy
            # sessions are bound to the loop that first connects them.
            engine = create_async_engine(self._db_url, connect_args={"timeout": 30})
            try:
                maker = async_sessionmaker(engine, expire_on_commit=False)
                async with maker() as session:
                    yield UserManager(
                        SQLAlchemyUserDatabase(session, User, OAuthAccount)
                    )
            finally:
                await engine.dispose()

        async def _guard_override(request: Request) -> None:
            # ``self._actor`` is switched per test (e.g. to the OAuth-only
            # persona) so one TestClient can exercise every caller type.
            request.state.actor_user = self._actor

        main.app.dependency_overrides[main.get_user_manager] = _manager_override
        main.app.dependency_overrides[main.auth_guard] = _guard_override
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(self._existing_overrides)
        self._tmp.cleanup()

    # -- helpers -------------------------------------------------------------

    def _headers_a(self) -> dict[str, str]:
        return {"Authorization": "Bearer test-token"}

    def _login(self, username: str, password: str):
        return self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )

    def _assert_refusal(self, response, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, response.text)
        body = response.json()
        self.assertEqual(body["detail"]["code"], code)

    # -- GET /me -------------------------------------------------------------

    def test_read_me_returns_own_profile(self) -> None:
        response = self.client.get("/api/v1/users/me", headers=self._headers_a())
        self.assertEqual(response.status_code, 200, response.text)
        profile = response.json()
        self.assertEqual(profile["username"], USER_A)
        self.assertEqual(profile["email"], EMAIL_A)
        self.assertEqual(profile["role"], "reviewer")
        self.assertIsInstance(profile["id"], str)
        self.assertTrue(profile["is_active"])
        self.assertEqual(profile["oauth_providers"], [])

    # -- display name --------------------------------------------------------

    def test_update_profile_changes_display_name_without_password(self) -> None:
        response = self.client.patch(
            "/api/v1/users/me/profile",
            headers=self._headers_a(),
            json={"display_name": "Renamed Persona"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["display_name"], "Renamed Persona")

    # -- username ------------------------------------------------------------

    def test_change_username_rejects_wrong_current_password(self) -> None:
        response = self.client.patch(
            "/api/v1/users/me/username",
            headers=self._headers_a(),
            json={"username": "hijacked", "current_password": "wrong-password"},
        )
        self._assert_refusal(response, 400, "current_password_incorrect")

    def test_change_username_succeeds_and_new_name_can_log_in(self) -> None:
        new_name = "persona_a_new"
        response = self.client.patch(
            "/api/v1/users/me/username",
            headers=self._headers_a(),
            json={"username": new_name, "current_password": PASS_A},
        )
        self.assertEqual(response.status_code, 200, response.text)
        profile = response.json()
        self.assertEqual(profile["username"], new_name)
        # Registered accounts default display_name to the login name; renaming
        # the login should carry the display name along.
        self.assertEqual(profile["display_name"], new_name)
        # The new identity is what authenticates now.
        login = self._login(new_name, PASS_A)
        self.assertEqual(login.status_code, 200, login.text)
        old_login = self._login(USER_A, PASS_A)
        self.assertEqual(old_login.status_code, 401)

    def test_change_username_to_taken_name_conflicts(self) -> None:
        response = self.client.patch(
            "/api/v1/users/me/username",
            headers=self._headers_a(),
            json={"username": USER_B, "current_password": PASS_A},
        )
        self._assert_refusal(response, 409, "username_taken")

    def test_change_username_same_value_is_idempotent(self) -> None:
        response = self.client.patch(
            "/api/v1/users/me/username",
            headers=self._headers_a(),
            json={"username": USER_A, "current_password": PASS_A},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["username"], USER_A)

    # -- email ---------------------------------------------------------------

    def test_change_email_rejects_wrong_current_password(self) -> None:
        response = self.client.patch(
            "/api/v1/users/me/email",
            headers=self._headers_a(),
            json={"email": "taken@elsewhere.com", "current_password": "wrong"},
        )
        self._assert_refusal(response, 400, "current_password_incorrect")

    def test_change_email_rejects_bad_format(self) -> None:
        response = self.client.patch(
            "/api/v1/users/me/email",
            headers=self._headers_a(),
            json={"email": "not-an-email", "current_password": PASS_A},
        )
        self._assert_refusal(response, 400, "validation_failed")

    def test_change_email_to_taken_address_conflicts(self) -> None:
        response = self.client.patch(
            "/api/v1/users/me/email",
            headers=self._headers_a(),
            json={"email": EMAIL_B, "current_password": PASS_A},
        )
        self._assert_refusal(response, 409, "email_taken")

    def test_change_email_succeeds(self) -> None:
        new_email = "renamed@example.com"
        response = self.client.patch(
            "/api/v1/users/me/email",
            headers=self._headers_a(),
            json={"email": new_email, "current_password": PASS_A},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["email"], new_email)

    def test_change_email_case_variant_of_own_is_idempotent(self) -> None:
        response = self.client.patch(
            "/api/v1/users/me/email",
            headers=self._headers_a(),
            json={"email": EMAIL_A.upper(), "current_password": PASS_A},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["email"].lower(), EMAIL_A)

    # -- password ------------------------------------------------------------

    def test_change_password_rejects_wrong_current(self) -> None:
        response = self.client.post(
            "/api/v1/users/me/password",
            headers=self._headers_a(),
            json={"current_password": "wrong", "new_password": "BrandNew-123"},
        )
        self._assert_refusal(response, 400, "current_password_incorrect")

    def test_change_password_rotates_credential(self) -> None:
        new_pass = "BrandNew-123!"
        response = self.client.post(
            "/api/v1/users/me/password",
            headers=self._headers_a(),
            json={"current_password": PASS_A, "new_password": new_pass},
        )
        self.assertEqual(response.status_code, 200, response.text)
        old = self._login(USER_A, PASS_A)
        self.assertEqual(old.status_code, 401)
        fresh = self._login(USER_A, new_pass)
        self.assertEqual(fresh.status_code, 200, fresh.text)

    def test_change_password_must_differ(self) -> None:
        response = self.client.post(
            "/api/v1/users/me/password",
            headers=self._headers_a(),
            json={"current_password": PASS_A, "new_password": PASS_A},
        )
        self._assert_refusal(response, 400, "validation_failed")

    # -- set a first password (OAuth-only account) ---------------------------

    def _as_gh(self) -> None:
        self._actor = self._user_gh

    def _set_password(self, *, reauth: str, new_pass: str = "GhPassw0rd-99") -> object:
        return self.client.post(
            "/api/v1/users/me/set-password",
            headers=self._headers_a(),
            json={
                "new_password": new_pass,
                "confirm_password": new_pass,
                "reauth_token": reauth,
            },
        )

    def test_read_me_reports_oauth_account_has_no_password(self) -> None:
        self._as_gh()
        response = self.client.get("/api/v1/users/me", headers=self._headers_a())
        self.assertEqual(response.status_code, 200, response.text)
        profile = response.json()
        self.assertFalse(profile["has_password"])
        self.assertIn("github", profile["oauth_providers"])

    def test_password_login_fails_for_oauth_account_until_password_set(self) -> None:
        # Empty hash: there is no password to verify, and logging in must not
        # crash the password helper on an empty string.
        response = self._login(USER_GH, "any-password")
        self.assertEqual(response.status_code, 401)

    def test_oauth_account_cannot_edit_username_without_a_password(self) -> None:
        self._as_gh()
        response = self.client.patch(
            "/api/v1/users/me/username",
            headers=self._headers_a(),
            json={"username": "hijacked", "current_password": "whatever"},
        )
        self._assert_refusal(response, 400, "password_not_set")

    def test_oauth_account_cannot_edit_email_without_a_password(self) -> None:
        self._as_gh()
        response = self.client.patch(
            "/api/v1/users/me/email",
            headers=self._headers_a(),
            json={"email": "new@example.com", "current_password": "whatever"},
        )
        self._assert_refusal(response, 400, "password_not_set")

    def test_oauth_account_cannot_use_change_password_without_a_password(self) -> None:
        self._as_gh()
        response = self.client.post(
            "/api/v1/users/me/password",
            headers=self._headers_a(),
            json={"current_password": "whatever", "new_password": "BrandNew-123"},
        )
        self._assert_refusal(response, 400, "password_not_set")

    def test_set_password_rejected_without_a_valid_reauth_grant(self) -> None:
        self._as_gh()
        self._assert_refusal(self._set_password(reauth="garbage-token"), 400, "password_reauth_required")

    def test_set_password_rejected_with_another_users_reauth_grant(self) -> None:
        self._as_gh()
        # A grant minted for persona_a proves nothing about the signed-in
        # GitHub-only caller.
        other_grant = issue_reauth_token(self._user_a.id)
        self._assert_refusal(self._set_password(reauth=other_grant), 400, "password_reauth_required")

    def test_set_password_succeeds_with_own_reauth_and_unlocks_account(self) -> None:
        self._as_gh()
        grant = issue_reauth_token(self._user_gh.id)
        response = self._set_password(reauth=grant, new_pass="GhPassw0rd-99")
        self.assertEqual(response.status_code, 200, response.text)
        profile = response.json()
        self.assertTrue(profile["has_password"])

        # The new password authenticates now.
        login = self._login(EMAIL_GH, "GhPassw0rd-99")
        self.assertEqual(login.status_code, 200, login.text)
        # And the password-gated edits are unlocked (username change works).
        renamed = self.client.patch(
            "/api/v1/users/me/username",
            headers=self._headers_a(),
            json={"username": "persona_gh_renamed", "current_password": "GhPassw0rd-99"},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)

    def test_set_password_rejected_when_password_already_set(self) -> None:
        # persona_a already holds a real password: it must use change-password,
        # not set-password, even with a valid grant.
        grant = issue_reauth_token(self._user_a.id)
        response = self._set_password(reauth=grant, new_pass="Whatever-123")
        self._assert_refusal(response, 400, "password_already_set")

    def test_set_password_new_and_confirm_must_match(self) -> None:
        self._as_gh()
        grant = issue_reauth_token(self._user_gh.id)
        response = self.client.post(
            "/api/v1/users/me/set-password",
            headers=self._headers_a(),
            json={
                "new_password": "GhPassw0rd-99",
                "confirm_password": "Different-77",
                "reauth_token": grant,
            },
        )
        self._assert_refusal(response, 400, "validation_failed")

    # -- the stock router is gone (self-escalation closed) -------------------

    def test_patching_role_on_me_is_not_a_route(self) -> None:
        # The old fastapi-users router answered PATCH /users/me and honoured the
        # ``role`` field in UserUpdate — a reviewer could promote themselves.
        response = self.client.patch(
            "/api/v1/users/me",
            headers=self._headers_a(),
            json={"role": "admin"},
        )
        self.assertEqual(response.status_code, 405, response.text)

    def test_admin_user_patch_path_is_not_a_route(self) -> None:
        # The stock superuser routes (PATCH /users/{id}, DELETE /users/{id})
        # are gone too: no user directory is exposed at all.
        import uuid as _uuid

        target = str(_uuid.uuid4())
        self.assertEqual(
            self.client.patch(
                f"/api/v1/users/{target}", headers=self._headers_a(), json={}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/v1/users/{target}", headers=self._headers_a()
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
