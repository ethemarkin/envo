import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin

# Recognizable prefix so secret scanners (and people) can spot leaked tokens.
TOKEN_PREFIX = "envo_st_"  # noqa: S105 (a public prefix, not a secret)


class ServiceToken(IdMixin, TimestampMixin, Base):
    """A CI/CD credential scoped to one project and selected environments.

    It carries no role: it may read the listed environments and, with
    `can_write`, change them. Only the SHA-256 hash of the token is stored.
    """

    __tablename__ = "service_tokens"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # First characters after the prefix, shown in lists to tell tokens apart.
    hint: Mapped[str] = mapped_column(String(16))
    can_write: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    environments: Mapped[list["ServiceTokenEnvironment"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def environment_ids(self) -> set[uuid.UUID]:
        return {e.environment_id for e in self.environments}


class ServiceTokenEnvironment(Base):
    __tablename__ = "service_token_environments"

    token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_tokens.id", ondelete="CASCADE"), primary_key=True
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), primary_key=True
    )
