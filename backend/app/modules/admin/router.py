"""Instance administration: settings and administrator assignment."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import bad_request, forbidden, not_found
from app.modules.audit_logs.service import record
from app.modules.auth.models import User
from app.modules.authorization.access import get_settings_row

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise forbidden("admin_required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


class SettingsOut(BaseModel):
    allow_root_creation: bool


class SettingsUpdate(BaseModel):
    allow_root_creation: bool | None = None


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    is_admin: bool
    created_at: datetime


class AdminUserUpdate(BaseModel):
    is_admin: bool


@router.get("/settings", response_model=SettingsOut)
async def get_settings(admin: AdminUser, session: SessionDep) -> SettingsOut:
    row = await get_settings_row(session)
    await session.commit()
    return SettingsOut(allow_root_creation=row.allow_root_creation)


@router.patch("/settings", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate, admin: AdminUser, request: Request, session: SessionDep
) -> SettingsOut:
    row = await get_settings_row(session)
    if body.allow_root_creation is not None:
        row.allow_root_creation = body.allow_root_creation
    record(
        session,
        request,
        "admin.settings_updated",
        actor_user_id=admin.id,
        details=body.model_dump(exclude_none=True),
    )
    await session.commit()
    return SettingsOut(allow_root_creation=row.allow_root_creation)


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(admin: AdminUser, session: SessionDep):
    users = await session.scalars(select(User).order_by(User.created_at))
    return [
        AdminUserOut(
            id=u.id, email=u.email, name=u.name, is_admin=u.is_admin, created_at=u.created_at
        )
        for u in users
    ]


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    admin: AdminUser,
    request: Request,
    session: SessionDep,
):
    target = await session.get(User, user_id, with_for_update=True)
    if target is None:
        raise not_found("user_not_found")
    if target.is_admin and not body.is_admin:
        admins = await session.scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True))
        )
        if (admins or 0) <= 1:
            raise bad_request("last_admin")
    target.is_admin = body.is_admin
    record(
        session,
        request,
        "admin.user_updated",
        actor_user_id=admin.id,
        resource_type="user",
        resource_id=target.id,
        details={"is_admin": body.is_admin},
    )
    await session.commit()
    return AdminUserOut(
        id=target.id,
        email=target.email,
        name=target.name,
        is_admin=target.is_admin,
        created_at=target.created_at,
    )
