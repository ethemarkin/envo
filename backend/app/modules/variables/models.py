import uuid
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class Visibility(StrEnum):
    VISIBLE = "visible"
    SECRET = "secret"  # noqa: S105 (a visibility level, not a credential)


VisibilityType = Enum(
    Visibility, name="variable_visibility", values_callable=lambda e: [m.value for m in e]
)


class Variable(IdMixin, TimestampMixin, Base):
    """Current state of one key in one folder's .env of an environment. Every
    value is encrypted, visible ones included; visibility only controls
    masking and access."""

    __tablename__ = "variables"
    __table_args__ = (UniqueConstraint("environment_id", "path", "key"),)

    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    # Folder in the project tree; "" is the project root.
    path: Mapped[str] = mapped_column(String(255), default="", server_default="")
    key: Mapped[str] = mapped_column(String(255))
    visibility: Mapped[Visibility] = mapped_column(VisibilityType)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
