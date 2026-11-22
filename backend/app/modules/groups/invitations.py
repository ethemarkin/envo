"""Loading and redeeming invitation tokens.

Shared by the invitation link endpoints and sign-up: an account can only be
created with a pending invitation for the same e-mail address.
"""

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.errors import not_found
from app.core.security import hash_token
from app.modules.audit_logs.service import record
from app.modules.auth.models import User
from app.modules.authorization.policy import highest
from app.modules.groups.invitation_models import Invitation
from app.modules.groups.models import GroupMember
from app.modules.projects.models import ProjectMember


async def load_pending(session: AsyncSession, token: str, lock: bool = False) -> Invitation:
    """The pending invitation of a link token, or 404."""
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


async def redeem(session: AsyncSession, request: Request, inv: Invitation, user: User) -> None:
    """Grant what the invitation offers and mark it used. The caller checks
    that the e-mail matches and commits."""
    if inv.group_id is not None or inv.project_id is not None:
        assert inv.role is not None
        if inv.group_id is not None:
            model, column, target_id = GroupMember, GroupMember.group_id, inv.group_id
        else:
            model, column, target_id = ProjectMember, ProjectMember.project_id, inv.project_id
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
    # The link reached this address: the account's e-mail is proven.
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
        details={"role": inv.role.value if inv.role else None},
    )
