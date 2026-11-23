import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class ProjectFolder(IdMixin, TimestampMixin, Base):
    """A folder of the project's tree, shared by all environments. Each
    environment keeps its own .env for every folder (variables carry the
    folder's path). The root ("") always exists and is not stored.

    Writing a variable into a path creates the missing folders, so a rollback
    to a revision that used a since-deleted folder brings the folder back.
    """

    __tablename__ = "project_folders"
    __table_args__ = (UniqueConstraint("project_id", "path"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(255))
