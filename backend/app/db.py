"""Async SQLAlchemy engine and session factory for the users database.

The application previously stored users in a hand-rolled ``sqlite3`` table. We
now back authentication with ``fastapi-users``, which expects an async SQLAlchemy
``AsyncSession`` (aiosqlite on SQLite). The database lives under ``state_root``
alongside the other runtime state and is gitignored via ``var/*``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


_settings = get_settings()
_settings.state_root.mkdir(parents=True, exist_ok=True)

_DEFAULT_DATABASE_PATH = _settings.state_root / "auth.sqlite3"
DATABASE_URL = os.environ.get(
    "WATEREXPERT_DATABASE_URL",
    f"sqlite+aiosqlite:///{_DEFAULT_DATABASE_PATH}",
)

engine = create_async_engine(DATABASE_URL)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session."""
    async with async_session_maker() as session:
        yield session
