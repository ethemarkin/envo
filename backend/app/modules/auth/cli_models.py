import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class CliLoginStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CONSUMED = "consumed"


class CliLoginRequest(IdMixin, TimestampMixin, Base):
    """A pending `envo login`, approved by the signed-in user in the browser.

    The CLI holds the device code (only its hash is stored) and polls with it;
    the user types the short user code on the web page to approve.
    """

    __tablename__ = "cli_login_requests"

    device_code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_code: Mapped[str] = mapped_column(String(16), unique=True)
    client_name: Mapped[str | None] = mapped_column(String(200))
    client_ip: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[CliLoginStatus] = mapped_column(
        Enum(
            CliLoginStatus,
            name="cli_login_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=CliLoginStatus.PENDING,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
