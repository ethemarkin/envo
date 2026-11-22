import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Stored lower-cased; uniqueness is enforced on the normalized value.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    # Null only for accounts that cannot sign in with a password.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    email_verified: Mapped[bool] = mapped_column(default=False)
    # Instance administrators have owner rights everywhere and manage settings.
    # The first user to sign up becomes one.
    is_admin: Mapped[bool] = mapped_column(default=False, server_default="false")


class RefreshToken(IdMixin, TimestampMixin, Base):
    """Rotating refresh token. Only the SHA-256 hash of the token is stored.

    All tokens issued from one login share a family_id; presenting an already
    rotated token revokes the whole family (token theft detection).
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(500))
