"""Membership management shared by groups and projects.

A member list shows direct members of the node plus members inherited from
ancestor groups. Only direct memberships can be changed on a node; inherited
ones are managed on the group they come from.
"""

import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import Request
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.mail import Mail, deliver
from app.core.security import hash_token, new_opaque_token
from app.modules.audit_logs.service import record
from app.modules.auth.models import User
from app.modules.authorization.deps import GroupAccess, ProjectAccess
from app.modules.authorization.policy import Action, Role, can_assign_role
from app.modules.groups.invitation_models import Invitation
from app.modules.groups.models import GroupMember
from app.modules.projects.models import ProjectMember

INVITATION_TTL = timedelta(days=7)


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    name: str | None
    role: Role
    created_at: datetime
    inherited: bool
    source_type: Literal["group", "project"]
    source_id: uuid.UUID
    source_name: str


class MemberAdd(BaseModel):
    email: EmailStr
    role: Role

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class MemberUpdate(BaseModel):
    role: Role


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    created_at: datetime
    expires_at: datetime
    invited_by: str | None


class AddResult(BaseModel):
    """Adding an e-mail without an account sends an invitation instead."""

    type: Literal["member", "invitation"]
    member: MemberOut | None = None
    invitation: InvitationOut | None = None
    # Only when no e-mail could be sent: the inviter shares the link.
    invite_url: str | None = None


Access = GroupAccess | ProjectAccess


def _scope(access: Access):
    """(member model, scope column, node id, node name, is root node)."""
    if isinstance(access, GroupAccess):
        g = access.group
        return GroupMember, GroupMember.group_id, g.id, g.name, g.parent_id is None
    p = access.project
    return ProjectMember, ProjectMember.project_id, p.id, p.name, p.group_id is None


def _audit_scope(access: Access) -> dict:
    if isinstance(access, GroupAccess):
        return {"group_id": access.group.id}
    return {"project_id": access.project.id, "group_id": access.project.group_id}


async def list_members(session: AsyncSession, access: Access) -> list[MemberOut]:
    access.ensure(Action.MEMBER_READ)
    model, column, node_id, node_name, _ = _scope(access)
    out: list[MemberOut] = []
    direct = await session.scalars(
        select(model).where(column == node_id).order_by(model.created_at)
    )
    source_type = "group" if model is GroupMember else "project"
    for m in direct:
        out.append(_member_out(m, False, source_type, node_id, node_name))

    ancestors = access.chain[1:] if isinstance(access, GroupAccess) else access.chain
    names = {g.id: g.name for g in ancestors}
    if names:
        inherited = await session.scalars(
            select(GroupMember)
            .where(GroupMember.group_id.in_(names))
            .order_by(GroupMember.created_at)
        )
        for m in inherited:
            out.append(_member_out(m, True, "group", m.group_id, names[m.group_id]))
    return out


def _member_out(m, inherited: bool, source_type: str, source_id, source_name) -> MemberOut:
    return MemberOut(
        id=m.id,
        user_id=m.user_id,
        email=m.user.email,
        name=m.user.name,
        role=m.role,
        created_at=m.created_at,
        inherited=inherited,
        source_type=source_type,  # type: ignore[arg-type]
        source_id=source_id,
        source_name=source_name,
    )


async def _direct_owner_count(session: AsyncSession, model, column, node_id) -> int:
    # Lock the owner rows so two concurrent demotions cannot leave zero owners.
    rows = await session.scalars(
        select(model.id).where(column == node_id, model.role == Role.OWNER).with_for_update()
    )
    return len(rows.all())


async def add_member(
    session: AsyncSession, request: Request, access: Access, body: MemberAdd
) -> AddResult:
    access.ensure(Action.MEMBER_MANAGE)
    if not can_assign_role(access.role, None, body.role):
        raise forbidden()
    model, column, node_id, node_name, _ = _scope(access)
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None:
        return await create_invitation(session, request, access, body.email, body.role)
    member = model(user_id=user.id, role=body.role)
    setattr(member, column.key, node_id)
    session.add(member)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise conflict("already_member") from None
    record(
        session,
        request,
        "member.added",
        actor_user_id=access.user.id,
        resource_type="member",
        resource_id=member.id,
        details={"user_id": str(user.id), "role": body.role.value},
        **_audit_scope(access),
    )
    await session.commit()
    await session.refresh(member, ["user"])
    source_type = "group" if model is GroupMember else "project"
    return AddResult(
        type="member", member=_member_out(member, False, source_type, node_id, node_name)
    )


async def _get_direct(session: AsyncSession, access: Access, member_id: uuid.UUID):
    model, column, node_id, *_ = _scope(access)
    member = await session.scalar(
        select(model).where(model.id == member_id, column == node_id).with_for_update()
    )
    if member is None:
        raise not_found("member_not_found")
    return member


async def update_member(
    session: AsyncSession,
    request: Request,
    access: Access,
    member_id: uuid.UUID,
    body: MemberUpdate,
) -> MemberOut:
    access.ensure(Action.MEMBER_MANAGE)
    model, column, node_id, node_name, is_root = _scope(access)
    member = await _get_direct(session, access, member_id)
    if not can_assign_role(access.role, member.role, body.role):
        raise forbidden()
    if is_root and member.role == Role.OWNER and body.role != Role.OWNER:
        if await _direct_owner_count(session, model, column, node_id) <= 1:
            raise bad_request("last_owner")
    previous = member.role
    member.role = body.role
    record(
        session,
        request,
        "member.role_changed",
        actor_user_id=access.user.id,
        resource_type="member",
        resource_id=member.id,
        details={"user_id": str(member.user_id), "from": previous.value, "to": body.role.value},
        **_audit_scope(access),
    )
    await session.commit()
    source_type = "group" if model is GroupMember else "project"
    return _member_out(member, False, source_type, node_id, node_name)


async def remove_member(
    session: AsyncSession, request: Request, access: Access, member_id: uuid.UUID
) -> None:
    model, column, node_id, _, is_root = _scope(access)
    member = await _get_direct(session, access, member_id)
    leaving_self = member.user_id == access.user.id
    if not leaving_self:
        access.ensure(Action.MEMBER_MANAGE)
        if not can_assign_role(access.role, member.role, None):
            raise forbidden()
    if is_root and member.role == Role.OWNER:
        if await _direct_owner_count(session, model, column, node_id) <= 1:
            raise bad_request("last_owner")
    record(
        session,
        request,
        "member.left" if leaving_self else "member.removed",
        actor_user_id=access.user.id,
        resource_type="member",
        resource_id=member.id,
        details={"user_id": str(member.user_id), "role": member.role.value},
        **_audit_scope(access),
    )
    await session.delete(member)
    await session.commit()


# --- Invitations ----------------------------------------------------------------


def _invitation_target(access: Access) -> dict:
    if isinstance(access, GroupAccess):
        return {"group_id": access.group.id}
    return {"project_id": access.project.id}


def _invitation_column(access: Access):
    return Invitation.group_id if isinstance(access, GroupAccess) else Invitation.project_id


def _invitation_out(inv: Invitation, invited_by: str | None) -> InvitationOut:
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        role=inv.role,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        invited_by=invited_by,
    )


def invite_url(token: str) -> str:
    return f"{get_settings().frontend_url}/invite/{token}"


async def create_invitation(
    session: AsyncSession, request: Request, access: Access, email: str, role: Role
) -> AddResult:
    """Invite an e-mail address without an account. Inviting the same address
    again replaces the pending invitation (a fresh link, a fresh expiry)."""
    _, _, node_id, node_name, _ = _scope(access)
    column = _invitation_column(access)
    now = utcnow()
    await session.execute(
        update(Invitation)
        .where(
            column == node_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    token = new_opaque_token()
    inv = Invitation(
        email=email,
        role=role,
        token_hash=hash_token(token),
        invited_by_id=access.user.id,
        expires_at=now + INVITATION_TTL,
        **_invitation_target(access),
    )
    session.add(inv)
    await session.flush()
    record(
        session,
        request,
        "member.invited",
        actor_user_id=access.user.id,
        resource_type="invitation",
        resource_id=inv.id,
        details={"email": email, "role": role.value},
        **_audit_scope(access),
    )
    await session.commit()

    kind = "group" if isinstance(access, GroupAccess) else "proje"
    inviter = access.user.name or access.user.email
    url = invite_url(token)
    sent = await deliver(
        Mail(
            to=email,
            subject=f"Envo: {node_name} {kind} davetiniz",
            text=(
                f'{inviter} sizi Envo\'da "{node_name}" ({kind}) için {role.value} rolüyle '
                f"davet etti.\n\nDaveti kabul etmek için: {url}\n\n"
                "Bağlantı 7 gün geçerlidir. Bu daveti beklemiyorsanız e-postayı yok sayın.\n"
            ),
        )
    )
    return AddResult(
        type="invitation",
        invitation=_invitation_out(inv, inviter),
        invite_url=None if sent else url,
    )


async def list_invitations(session: AsyncSession, access: Access) -> list[InvitationOut]:
    """Pending (not accepted, revoked or expired) invitations of the node."""
    access.ensure(Action.MEMBER_MANAGE)
    _, _, node_id, *_ = _scope(access)
    rows = await session.execute(
        select(Invitation, User)
        .outerjoin(User, User.id == Invitation.invited_by_id)
        .where(
            _invitation_column(access) == node_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > utcnow(),
        )
        .order_by(Invitation.created_at)
    )
    return [_invitation_out(inv, (u.name or u.email) if u else None) for inv, u in rows]


async def revoke_invitation(
    session: AsyncSession, request: Request, access: Access, invitation_id: uuid.UUID
) -> None:
    access.ensure(Action.MEMBER_MANAGE)
    _, _, node_id, *_ = _scope(access)
    inv = await session.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id,
            _invitation_column(access) == node_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    )
    if inv is None:
        raise not_found("invitation_not_found")
    inv.revoked_at = utcnow()
    record(
        session,
        request,
        "member.invitation_revoked",
        actor_user_id=access.user.id,
        resource_type="invitation",
        resource_id=inv.id,
        details={"email": inv.email},
        **_audit_scope(access),
    )
    await session.commit()
