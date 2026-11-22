import uuid

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin
from app.modules.auth.models import User
from app.modules.authorization.policy import Role
from app.modules.groups.models import RoleType


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index(
            "uq_projects_root_slug", "slug", unique=True, postgresql_where=text("group_id IS NULL")
        ),
        Index(
            "uq_projects_group_slug",
            "group_id",
            "slug",
            unique=True,
            postgresql_where=text("group_id IS NOT NULL"),
        ),
    )

    # Null for projects at the root of the instance.
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)


class ProjectMember(IdMixin, TimestampMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(RoleType)

    user: Mapped[User] = relationship(lazy="joined", innerjoin=True)
