import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.slugs import SLUG_PATTERN


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    protected: bool = False


class EnvironmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    protected: bool | None = None


class EnvironmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    slug: str
    protected: bool
    revision: int
    created_at: datetime
    updated_at: datetime
