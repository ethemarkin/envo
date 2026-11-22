"""Accepting an invitation from the link in the e-mail.

The preview is public (the link token is the secret). Accepting requires a
signed-in user whose e-mail matches the invitation, which also proves the
address: the account is marked as verified.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.db import utcnow
from app.core.deps import CurrentUser, SessionDep
from app.core.errors import forbidden, not_found
from app.core.security import hash_token
from app.modules.audit_logs.service import record
from app.modules.auth.models import User
from app.modules.authorization.access import ancestor_chain, path_of
from app.modules.authorization.policy import Role, highest
from app.modules.groups.invitation_models import Invitation
from app.modules.groups.models import Group, GroupMember
from app.modules.projects.models import Project, ProjectMember

router = APIRouter(prefix="/api/invitations", tags=["invitations"])


class InvitationPreview(BaseModel):
    target_type: Literal["group", "project"]
    target_id: uuid.UUID
    target_name: str
    target_path: str
    role: Role
    email: str
    invited_by: str | None
    expires_at: datetime


class AcceptOut(BaseModel):
    target_type: Literal["group", "project"]
    target_id: uuid.UUID


async def _load(session, token: str, lock: bool = False) -> Invitation:
    q = select(Invitation).where(Invitation.token_hash == hash_token(token))
    if lock:
        q = q.with_for_update()
    inv = await session.scalar(q)
    if (
        inv is None
        or inv.accepted_at is not None
        or inv.revoked_at is not None
        or inv.expires_at <= utcnow()
    ):
        raise not_found("invitation_not_found")
    return inv


async def _target(session, inv: Invitation):
    if inv.group_id is not None:
        group = await session.get(Group, inv.group_id)
        chain = await ancestor_chain(session, inv.group_id)
        return "group", group.id, group.name, path_of(chain)
    project = await session.get(Project, inv.project_id)
    chain = await ancestor_chain(session, project.group_id)
    return "project", project.id, project.name, path_of(chain, project.slug)


@router.get("/{token}", response_model=InvitationPreview)
async def preview(token: str, session: SessionDep) -> InvitationPreview:
    inv = await _load(session, token)
    target_type, target_id, name, path = await _target(session, inv)
    inviter = await session.get(User, inv.invited_by_id) if inv.invited_by_id else None
    return InvitationPreview(
        target_type=target_type,
        target_id=target_id,
        target_name=name,
        target_path=path,
        role=inv.role,
        email=inv.email,
        invited_by=(inviter.name or inviter.email) if inviter else None,
        expires_at=inv.expires_at,
    )


@router.post("/{token}/accept", response_model=AcceptOut)
async def accept(token: str, user: CurrentUser, request: Request, session: SessionDep):
    inv = await _load(session, token, lock=True)
    if user.email != inv.email:
        raise forbidden("invitation_email_mismatch")

    if inv.group_id is not None:
        model, column, target_id, target_type = (
            GroupMember,
            GroupMember.group_id,
            inv.group_id,
            "group",
        )
    else:
        model, column, target_id, target_type = (
            ProjectMember,
            ProjectMember.project_id,
            inv.project_id,
            "project",
        )
    existing = await session.scalar(
        select(model).where(column == target_id, model.user_id == user.id).with_for_update()
    )
    if existing is None:
        member = model(user_id=user.id, role=inv.role)
        setattr(member, column.key, target_id)
        session.add(member)
    else:
        # Accepting never lowers an existing role.
        existing.role = highest([existing.role, inv.role])

    inv.accepted_at = utcnow()
    inv.accepted_by_id = user.id
    user.email_verified = True
    record(
        session,
        request,
        "member.invitation_accepted",
        actor_user_id=user.id,
        group_id=inv.group_id,
        project_id=inv.project_id,
        resource_type="invitation",
        resource_id=inv.id,
        details={"role": inv.role.value},
    )
    await session.commit()
    return AcceptOut(target_type=target_type, target_id=target_id)
