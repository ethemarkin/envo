import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.slugs import SLUG_PATTERN
from app.modules.authorization.policy import Role
from app.modules.groups.schemas import BreadcrumbOut


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=2000)
    # None creates a top-level project.
    group_id: uuid.UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=2000)


class ProjectOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID | None
    name: str
    slug: str
    path: str
    description: str | None
    role: Role
    ancestors: list[BreadcrumbOut]
    created_at: datetime
    updated_at: datetime
