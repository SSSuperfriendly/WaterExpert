"""Shared HTTP refusal helper and email validation.

A single definition of the stable ``{code, detail}`` refusal shape, so a route
in ``main`` and the self-service router cannot drift apart. Importing this
module pulls in no service, which is what lets ``self_service`` use it without
the circular import the previous private copy existed to avoid.
"""

from __future__ import annotations

import re

from fastapi import HTTPException

from backend.app.domain.codes import ErrorCode

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def error_response(code: ErrorCode, detail: str, status_code: int) -> HTTPException:
    """A refusal the frontend can localise.

    ``code`` is stable and drives the UI's message catalogue; ``detail`` stays
    English for operators and logs (review item 22).
    """
    return HTTPException(status_code=status_code, detail={"code": str(code), "detail": detail})
