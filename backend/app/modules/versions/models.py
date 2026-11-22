"""Append-only change history per environment.

Each write bumps `environments.revision` and records one EnvironmentRevision
(the change set) plus one VariableRevision per changed key holding the key's
full state after the change. The state at revision N is the latest
VariableRevision per key with revision <= N, minus deleted keys.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Index, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.modules.variables.models import Visibility, VisibilityType


class ChangeSource(StrEnum):
    WEB = "web"
    CLI = "cli"
    TOKEN = "token"  # noqa: S105 (a change source, not a credential)
    ROLLBACK = "rollback"


class ChangeAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class EnvironmentRevision(IdMixin, TimestampMixin, Base):
    __tablename__ = "environment_revisions"
    __table_args__ = (UniqueConstraint("environment_id", "revision"),)

    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE")
    )
    revision: Mapped[int]
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    source: Mapped[ChangeSource] = mapped_column(
        Enum(ChangeSource, name="change_source", values_callable=lambda e: [m.value for m in e])
    )
    message: Mapped[str | None] = mapped_column(String(500))


class VariableRevision(IdMixin, TimestampMixin, Base):
    __tablename__ = "variable_revisions"
    __table_args__ = (Index(None, "environment_id", "key", "revision"),)

    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE")
    )
    revision: Mapped[int]
    key: Mapped[str] = mapped_column(String(255))
    action: Mapped[ChangeAction] = mapped_column(
        Enum(ChangeAction, name="change_action", values_callable=lambda e: [m.value for m in e])
    )
    # State after the change; null for deletes.
    visibility: Mapped[Visibility | None] = mapped_column(VisibilityType)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
