import uuid

from sqlalchemy import ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin

# Created with every new project. Production starts protected.
DEFAULT_ENVIRONMENTS: list[tuple[str, str, bool]] = [
    ("Development", "development", False),
    ("Staging", "staging", False),
    ("Production", "production", True),
]


class Environment(IdMixin, TimestampMixin, Base):
    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("project_id", "slug"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    # Used by the CLI: `envo pull --env <slug>`.
    slug: Mapped[str] = mapped_column(String(64))
    protected: Mapped[bool] = mapped_column(default=False)
    # Incremented on every variable write; also the optimistic lock.
    revision: Mapped[int] = mapped_column(default=0)
    # The environment's data key, wrapped by the master key `kek_id`. Created
    # on first write; deleting the environment deletes the key.
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary)
    kek_id: Mapped[str | None] = mapped_column(String(64))
