"""SQLAlchemy models for users and their OAuth accounts.

Extends ``fastapi-users-db-sqlalchemy`` base tables (UUID primary keys, email,
hashed password, active/superuser/verified flags) with the domain columns the
WaterExpert workbench needs: a unique ``username`` (login identifier), a human
``display_name``, and an application ``role``.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fastapi_users_db_sqlalchemy import (
    SQLAlchemyBaseOAuthAccountTableUUID,
    SQLAlchemyBaseUserTableUUID,
)

from backend.app.db import Base

USERNAME_MAX = 64
DISPLAY_NAME_MAX = 120
ROLE_MAX = 32


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "user"

    username: Mapped[str] = mapped_column(
        String(USERNAME_MAX), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(
        String(DISPLAY_NAME_MAX), nullable=False, default=""
    )
    role: Mapped[str] = mapped_column(
        String(ROLE_MAX), nullable=False, default="reviewer"
    )

    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        "OAuthAccount",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    __tablename__ = "oauth_account"

    user: Mapped["User"] = relationship(
        "User", back_populates="oauth_accounts"
    )
