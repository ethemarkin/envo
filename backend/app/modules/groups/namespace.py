"""Groups and projects share one namespace per parent, like GitLab paths:
"acme/backend" cannot be both a subgroup and a project."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import conflict
from app.core.slugs import slugify
from app.modules.groups.models import Group
from app.modules.projects.models import Project


async def slug_taken(
    session: AsyncSession,
    parent_id: uuid.UUID | None,
    slug: str,
    *,
    except_group: uuid.UUID | None = None,
    except_project: uuid.UUID | None = None,
) -> bool:
    group_q = select(Group.id).where(
        Group.slug == slug,
        Group.parent_id.is_(None) if parent_id is None else Group.parent_id == parent_id,
    )
    if except_group is not None:
        group_q = group_q.where(Group.id != except_group)
    project_q = select(Project.id).where(
        Project.slug == slug,
        Project.group_id.is_(None) if parent_id is None else Project.group_id == parent_id,
    )
    if except_project is not None:
        project_q = project_q.where(Project.id != except_project)
    return (await session.scalar(group_q)) is not None or (
        await session.scalar(project_q)
    ) is not None


async def choose_slug(
    session: AsyncSession,
    parent_id: uuid.UUID | None,
    requested: str | None,
    name: str,
    fallback: str,
) -> str:
    """Use the requested slug (409 if taken) or derive a free one from the name."""
    if requested:
        if await slug_taken(session, parent_id, requested):
            raise conflict("slug_taken")
        return requested
    base = slugify(name, fallback)
    candidate, n = base, 2
    while await slug_taken(session, parent_id, candidate):
        candidate = f"{base[:60]}-{n}"
        n += 1
    return candidate
