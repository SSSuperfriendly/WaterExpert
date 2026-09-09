"""Registration gate (review item 6 / production hardening).

Open self-signup via ``POST /api/v1/auth/register`` creates ``reviewer``
accounts and is a compute/abuse surface on a public deployment. Production
disables it (``WATEREXPERT_ENABLE_REGISTRATION=0``); the default stays True so
local dev and the e2e chain keep working. These tests pin both sides of the
gate. The route's ``user_manager`` dependency is stubbed so the tests exercise
the gate without a real auth DB.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from fastapi.testclient import TestClient

from backend.app import main


class RegistrationGateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._original_settings = main.settings
        self._original_override = dict(main.app.dependency_overrides)
        # The gate runs before the manager is ever used; a bare stub is enough.
        main.app.dependency_overrides[main.get_user_manager] = lambda: object()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(self._original_override)
        main.settings = self._original_settings

    def _payload(self) -> dict[str, str]:
        return {
            "username": "new_user",
            "email": "new_user@example.com",
            "password": "secret-pass-123",
            "confirm_password": "secret-pass-123",
        }

    def test_register_disabled_returns_403(self) -> None:
        main.settings = replace(self._original_settings, enable_registration=False)
        response = self.client.post("/api/v1/auth/register", json=self._payload())
        self.assertEqual(response.status_code, 403)
        self.assertIn("disabled", response.json()["detail"])

    def test_register_enabled_still_validates_payload(self) -> None:
        # Default is True: the gate is open, so normal request validation runs.
        main.settings = self._original_settings
        payload = self._payload()
        payload["confirm_password"] = "different-password"
        response = self.client.post("/api/v1/auth/register", json=payload)
        self.assertEqual(response.status_code, 400)  # password mismatch, not 403


if __name__ == "__main__":
    unittest.main()
