"""Shared UTC timestamp formatting for backend state and reports."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> str:
    """Current UTC time as a second-precision ISO 8601 string with a ``Z`` suffix.

    One definition so every persisted ``created_at`` / ``updated_at`` column and
    every status payload carries the same format.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
