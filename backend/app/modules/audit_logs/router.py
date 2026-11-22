"""Reading the audit trail: per project, per group (including everything
below it) and instance-wide for administrators. Newest first, paginated with
an opaque cursor (the last event's id)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import SessionDep
from app.core.errors import bad_request
from app.modules.admin.router import AdminUser
from app.modules.audit_logs.actors import ActorLabels, ActorOut
from app.modules.audit_logs.models import AuditEvent
from app.modules.authorization.deps import GroupAccessDep, ProjectAccessDep
from app.modules.authorization.policy import Action
from app.modules.groups.models import Group
from app.modules.projects.models import Project

router = APIRouter(tags=["audit"])


class AuditEventOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    action: str
    actor: ActorOut
    resource_type: str | None
    resource_id: uuid.UUID | None
    group_id: uuid.UUID | None
    project_id: uuid.UUID | None
    ip: str | None
    user_agent: str | None
    details: dict[str, Any]


class AuditPage(BaseModel):
    events: list[AuditEventOut]
    next_before: uuid.UUID | None


Limit = Annotated[int, Query(ge=1, le=200)]
Before = Annotated[uuid.UUID | None, Query()]
# Prefix filter, e.g. "variables." or "member.".
ActionFilter = Annotated[str | None, Query(max_length=64)]


async def page(
    session: AsyncSession,
    query: Select,
    limit: int,
    before: uuid.UUID | None,
    action: str | None,
) -> AuditPage:
    if action:
        query = query.where(AuditEvent.action.startswith(action, autoescape=True))
    if before is not None:
        cursor = await session.get(AuditEvent, before)
        if cursor is None:
            raise bad_request("invalid_cursor")
        query = query.where(
            or_(
                AuditEvent.created_at < cursor.created_at,
                and_(AuditEvent.created_at == cursor.created_at, AuditEvent.id < cursor.id),
            )
        )
    rows = list(
        await session.scalars(
            query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    labels = await ActorLabels.load(
        session,
        {e.actor_user_id for e in rows if e.actor_user_id},
        {e.actor_token_id for e in rows if e.actor_token_id},
    )
    return AuditPage(
        events=[
            AuditEventOut(
                id=e.id,
                created_at=e.created_at,
                action=e.action,
                actor=labels.actor(e.actor_user_id, e.actor_token_id),
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                group_id=e.group_id,
                project_id=e.project_id,
                ip=e.ip,
                user_agent=e.user_agent,
                details=e.details,
            )
            for e in rows
        ],
        next_before=rows[-1].id if has_more else None,
    )


@router.get("/api/projects/{project_id}/audit-events", response_model=AuditPage)
async def project_events(
    access: ProjectAccessDep,
    session: SessionDep,
    limit: Limit = 50,
    before: Before = None,
    action: ActionFilter = None,
):
    access.ensure(Action.AUDIT_READ)
    query = select(AuditEvent).where(AuditEvent.project_id == access.project.id)
    return await page(session, query, limit, before, action)


@router.get("/api/groups/{group_id}/audit-events", response_model=AuditPage)
async def group_events(
    access: GroupAccessDep,
    session: SessionDep,
    limit: Limit = 50,
    before: Before = None,
    action: ActionFilter = None,
):
    """Events of the group, its subgroups and all projects below it."""
    access.ensure(Action.AUDIT_READ)
    subtree = select(Group.id).where(Group.id == access.group.id).cte("subtree", recursive=True)
    subtree = subtree.union_all(select(Group.id).join(subtree, Group.parent_id == subtree.c.id))
    group_ids = select(subtree.c.id)
    project_ids = select(Project.id).where(Project.group_id.in_(group_ids))
    query = select(AuditEvent).where(
        or_(AuditEvent.group_id.in_(group_ids), AuditEvent.project_id.in_(project_ids))
    )
    return await page(session, query, limit, before, action)


@router.get("/api/admin/audit-events", response_model=AuditPage)
async def instance_events(
    admin: AdminUser,
    session: SessionDep,
    limit: Limit = 50,
    before: Before = None,
    action: ActionFilter = None,
):
    """Everything, including sign-ins and instance administration."""
    return await page(session, select(AuditEvent), limit, before, action)
