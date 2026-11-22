from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin

SETTINGS_ID = 1


class InstanceSettings(TimestampMixin, Base):
    """Instance-wide settings; exactly one row (id = 1)."""

    __tablename__ = "instance_settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=SETTINGS_ID)
    # Whether non-admin users may create top-level groups and projects.
    allow_root_creation: Mapped[bool] = mapped_column(default=True)
