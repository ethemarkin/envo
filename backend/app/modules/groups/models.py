import uuid

from sqlalchemy import Enum, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin
from app.modules.auth.models import User
from app.modules.authorization.policy import Role

RoleType = Enum(Role, name="member_role", values_callable=lambda e: [m.value for m in e])


class Group(IdMixin, TimestampMixin, Base):
    """A folder of projects and subgroups. Membership is inherited downwards.

    Groups and projects share one namespace per parent: a slug identifies at
    most one group or project under the same parent (checked in the API).
    """

    __tablename__ = "groups"
    __table_args__ = (
        Index(
            "uq_groups_root_slug", "slug", unique=True, postgresql_where=text("parent_id IS NULL")
        ),
        Index(
            "uq_groups_parent_slug",
            "parent_id",
            "slug",
            unique=True,
            postgresql_where=text("parent_id IS NOT NULL"),
        ),
    )

    # Deleting a group deletes its subgroups and projects.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)


class GroupMember(IdMixin, TimestampMixin, Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id"),)

    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(RoleType)

    # Inner join so rows can be locked with SELECT ... FOR UPDATE.
    user: Mapped[User] = relationship(lazy="joined", innerjoin=True)
