"""Instance administration: settings, users and sign-up invitations."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func, select, update

from app.core.db import utcnow
from app.core.deps import CurrentUser, SessionDep
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.mail import Mail, deliver
from app.core.security import hash_token, new_opaque_token
from app.modules.audit_logs.service import record
from app.modules.auth.models import User
from app.modules.authorization.access import get_settings_row
from app.modules.authorization.members import INVITATION_TTL, invite_url
from app.modules.groups.invitation_models import Invitation

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


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: uuid.UUID, admin: AdminUser, request: Request, session: SessionDep):
    """Delete an account. Its memberships and sessions go with it; what it
    created (projects, variables, history) stays. Administrators cannot delete
    themselves, so at least one administrator always remains."""
    if user_id == admin.id:
        raise bad_request("cannot_delete_self")
    target = await session.get(User, user_id, with_for_update=True)
    if target is None:
        raise not_found("user_not_found")
    record(
        session,
        request,
        "admin.user_deleted",
        actor_user_id=admin.id,
        resource_type="user",
        resource_id=target.id,
        details={"email": target.email, "is_admin": target.is_admin},
    )
    await session.delete(target)
    await session.commit()


# --- Sign-up invitations ---------------------------------------------------------


class InstanceInvite(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class InstanceInvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime
    expires_at: datetime
    invited_by: str | None


class InstanceInviteResult(BaseModel):
    invitation: InstanceInvitationOut
    # Only when no e-mail could be sent: the administrator shares the link.
    invite_url: str | None = None


def _pending_instance_invitations():
    return (
        Invitation.group_id.is_(None),
        Invitation.project_id.is_(None),
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
    )


def _invitation_out(inv: Invitation, invited_by: str | None) -> InstanceInvitationOut:
    return InstanceInvitationOut(
        id=inv.id,
        email=inv.email,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        invited_by=invited_by,
    )


@router.post(
    "/invitations", response_model=InstanceInviteResult, status_code=status.HTTP_201_CREATED
)
async def invite(body: InstanceInvite, admin: AdminUser, request: Request, session: SessionDep):
    """Invite someone to sign up without giving access to anything yet.
    Inviting the same address again replaces the pending invitation."""
    if await session.scalar(select(User.id).where(User.email == body.email)):
        raise conflict("email_taken")
    now = utcnow()
    await session.execute(
        update(Invitation)
        .where(Invitation.email == body.email, *_pending_instance_invitations())
        .values(revoked_at=now)
    )
    token = new_opaque_token()
    inv = Invitation(
        email=body.email,
        role=None,
        token_hash=hash_token(token),
        invited_by_id=admin.id,
        expires_at=now + INVITATION_TTL,
    )
    session.add(inv)
    await session.flush()
    record(
        session,
        request,
        "admin.user_invited",
        actor_user_id=admin.id,
        resource_type="invitation",
        resource_id=inv.id,
        details={"email": body.email},
    )
    await session.commit()

    inviter = admin.name or admin.email
    url = invite_url(token)
    sent = await deliver(
        Mail(
            to=body.email,
            subject="Envo davetiniz",
            text=(
                f"{inviter} sizi Envo'ya davet etti.\n\nHesap oluşturmak için: {url}\n\n"
                "Bağlantı 7 gün geçerlidir. Bu daveti beklemiyorsanız e-postayı yok sayın.\n"
            ),
        )
    )
    return InstanceInviteResult(
        invitation=_invitation_out(inv, inviter), invite_url=None if sent else url
    )


@router.get("/invitations", response_model=list[InstanceInvitationOut])
async def list_invitations(admin: AdminUser, session: SessionDep):
    """Pending sign-up invitations sent by administrators."""
    rows = await session.execute(
        select(Invitation, User)
        .outerjoin(User, User.id == Invitation.invited_by_id)
        .where(*_pending_instance_invitations(), Invitation.expires_at > utcnow())
        .order_by(Invitation.created_at)
    )
    return [_invitation_out(inv, (u.name or u.email) if u else None) for inv, u in rows]


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: uuid.UUID, admin: AdminUser, request: Request, session: SessionDep
):
    inv = await session.scalar(
        select(Invitation).where(Invitation.id == invitation_id, *_pending_instance_invitations())
    )
    if inv is None:
        raise not_found("invitation_not_found")
    inv.revoked_at = utcnow()
    record(
        session,
        request,
        "admin.invitation_revoked",
        actor_user_id=admin.id,
        resource_type="invitation",
        resource_id=inv.id,
        details={"email": inv.email},
    )
    await session.commit()
