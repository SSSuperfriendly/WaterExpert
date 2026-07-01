from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthProfile:
    username: str
    display_name: str
    role: str


class DemoAuthService:
    def __init__(self) -> None:
        self._username = os.environ.get("WATEREXPERT_DEMO_USERNAME", "2510709")
        self._password = os.environ.get("WATEREXPERT_DEMO_PASSWORD", "AI4S666")
        self._display_name = os.environ.get("WATEREXPERT_DEMO_DISPLAY_NAME", "AI4S Demo User")
        self._role = os.environ.get("WATEREXPERT_DEMO_ROLE", "reviewer")

    def authenticate(self, username: str, password: str) -> AuthProfile | None:
        normalized_username = str(username or "").strip()
        normalized_password = str(password or "")
        if normalized_username != self._username or normalized_password != self._password:
            return None
        return AuthProfile(
            username=self._username,
            display_name=self._display_name,
            role=self._role,
        )

    def credential_hint(self) -> dict[str, str]:
        return {
            "username": self._username,
            "password": self._password,
        }
