"""The User table: one row per person who can sign in."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UserRole(StrEnum):
    """Coarse-grained role. A household owner trades; an operator watches the
    whole feeder. Enforced by the `require_role` dependency, not by the token
    alone — a token only proves identity, never authorization by itself."""

    HOUSEHOLD = "household"
    OPERATOR = "operator"
    ADMIN = "admin"


class User(Base):
    """A person who can sign in — a household owner, an operator, or an admin."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[UserRole] = mapped_column(
        # values_callable stores the StrEnum *value* ("household") rather than
        # SQLAlchemy's default of the member *name* ("HOUSEHOLD") — keeping the
        # database in sync with every other place a role is serialized (JWT
        # claims, API responses).
        Enum(
            UserRole,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=UserRole.HOUSEHOLD,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
