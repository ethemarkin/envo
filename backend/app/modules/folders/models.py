import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class ProjectFolder(IdMixin, TimestampMixin, Base):
    """A folder of the project's tree, shared by all environments. Folders are
    structure only; ProjectEnvFile says where a .env lives (variables carry
    its path). The root ("") always exists and is not stored.

    Writing a variable into a path creates the missing folders, so a rollback
    to a revision that used a since-deleted folder brings the folder back.
    """

    __tablename__ = "project_folders"
    __table_args__ = (UniqueConstraint("project_id", "path"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(255))


class ProjectEnvFile(IdMixin, TimestampMixin, Base):
    """A place in the project's tree that holds a .env: the root ("") or a
    folder. Folders are only structure; a .env exists where one of these rows
    says so, in every environment of the project.

    Writing a variable into a path adds the row (and the folders above it),
    so a rollback or a CLI push never leaves values without a visible .env.
    """

    __tablename__ = "project_env_files"
    __table_args__ = (UniqueConstraint("project_id", "path"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(255))
