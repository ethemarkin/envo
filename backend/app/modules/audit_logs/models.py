import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class AuditEvent(IdMixin, TimestampMixin, Base):
    """Who did what, where. Never contains variable values, passwords or tokens."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index(None, "project_id", "created_at"),
        Index(None, "group_id", "created_at"),
    )

    # Plain ids without foreign keys: the trail outlives deleted projects and groups.
    group_id: Mapped[uuid.UUID | None]
    project_id: Mapped[uuid.UUID | None]
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Set instead of actor_user_id when a service token acted (no FK: kept
    # after the token is deleted).
    actor_token_id: Mapped[uuid.UUID | None]
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str | None] = mapped_column(String(32))
    resource_id: Mapped[uuid.UUID | None]
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
