import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.slugs import SLUG_PATTERN
from app.modules.authorization.policy import Role


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=2000)
    # None creates a top-level group.
    parent_id: uuid.UUID | None = None


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=2000)


class BreadcrumbOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class GroupOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    slug: str
    path: str
    description: str | None
    role: Role
    # Ancestors from the top-level group down to the parent.
    ancestors: list[BreadcrumbOut]
    created_at: datetime


class ChildOut(BaseModel):
    id: uuid.UUID
    type: str  # "group" | "project"
    name: str
    slug: str
    description: str | None
