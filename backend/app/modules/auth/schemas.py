import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    name: str | None = Field(default=None, max_length=200)
    # Required except for the very first account of an instance.
    invite_token: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    email_verified: bool
    is_admin: bool


class RegistrationOut(BaseModel):
    # False only before the first account exists: that one needs no invitation.
    invitation_required: bool
