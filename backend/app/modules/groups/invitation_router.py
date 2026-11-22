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

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import forbidden
from app.modules.auth.models import User
from app.modules.authorization.access import ancestor_chain, path_of
from app.modules.authorization.policy import Role
from app.modules.groups import invitations
from app.modules.groups.invitation_models import Invitation
from app.modules.groups.models import Group
from app.modules.projects.models import Project

router = APIRouter(prefix="/api/invitations", tags=["invitations"])

TargetType = Literal["group", "project", "instance"]


class InvitationPreview(BaseModel):
    # "instance": an administrator's invitation to sign up, without a target.
    target_type: TargetType
    target_id: uuid.UUID | None
    target_name: str | None
    target_path: str | None
    role: Role | None
    email: str
    invited_by: str | None
    expires_at: datetime


class AcceptOut(BaseModel):
    target_type: TargetType
    target_id: uuid.UUID | None


async def _target(session, inv: Invitation):
    if inv.group_id is not None:
        group = await session.get(Group, inv.group_id)
        chain = await ancestor_chain(session, inv.group_id)
        return "group", group.id, group.name, path_of(chain)
    if inv.project_id is not None:
        project = await session.get(Project, inv.project_id)
        chain = await ancestor_chain(session, project.group_id)
        return "project", project.id, project.name, path_of(chain, project.slug)
    return "instance", None, None, None


@router.get("/{token}", response_model=InvitationPreview)
async def preview(token: str, session: SessionDep) -> InvitationPreview:
    inv = await invitations.load_pending(session, token)
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
    inv = await invitations.load_pending(session, token, lock=True)
    if user.email != inv.email:
        raise forbidden("invitation_email_mismatch")
    target_type, target_id, *_ = await _target(session, inv)
    await invitations.redeem(session, request, inv, user)
    await session.commit()
    return AcceptOut(target_type=target_type, target_id=target_id)
