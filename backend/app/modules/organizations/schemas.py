import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.slugs import SLUG_PATTERN
from app.modules.authorization.policy import Role


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: Role
    created_at: datetime


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    name: str | None
    role: Role
    created_at: datetime


class MemberUpdate(BaseModel):
    role: Role
