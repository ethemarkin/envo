from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.variables.models import Visibility


class VariableOut(BaseModel):
    # Folder whose .env holds the key; "" is the project root.
    path: str
    key: str
    visibility: Visibility
    # Only filled for visible variables; secrets need an explicit reveal.
    value: str | None
    updated_at: datetime


class FileOut(BaseModel):
    # A config file that has content in the environment.
    path: str
    name: str
    updated_at: datetime


class VariableListOut(BaseModel):
    revision: int
    protected: bool
    can_read_secrets: bool
    can_write: bool
    variables: list[VariableOut]
    files: list[FileOut]


class RevealIn(BaseModel):
    # None reveals every secret in the environment.
    keys: list[str] | None = Field(default=None, max_length=1000)


class RevealOut(BaseModel):
    values: dict[str, str]


class VariableSetIn(BaseModel):
    key: str = Field(max_length=255)
    value: str | None = None
    visibility: Visibility | None = None


class BatchIn(BaseModel):
    upserts: list[VariableSetIn] = Field(default_factory=list, max_length=1000)
    deletes: list[str] = Field(default_factory=list, max_length=1000)


class SingleSetIn(BaseModel):
    value: str
    visibility: Visibility | None = None


class FileContentIn(BaseModel):
    # The whole file as text; "" clears it.
    content: str


class WriteOut(BaseModel):
    revision: int
    created: list[str]
    updated: list[str]
    deleted: list[str]


class ImportIn(BaseModel):
    content: str
    # Visibility for keys that do not exist yet; existing keys keep theirs.
    # Keys not listed are created as secrets.
    visibility: dict[str, Visibility] = Field(default_factory=dict)
    dry_run: bool = False
    # Delete the folder's keys that the document does not contain.
    replace: bool = False


class ImportItem(BaseModel):
    key: str
    status: Literal["new", "changed", "unchanged", "deleted"]
    visibility: Visibility


class ImportOut(BaseModel):
    revision: int
    dry_run: bool
    items: list[ImportItem]


class DotenvErrorOut(BaseModel):
    line: int
    code: str
    message: str
