import uuid

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import SessionDep
from app.core.errors import conflict, not_found
from app.core.slugs import slugify, unique_slug
from app.modules.authorization.deps import MembershipDep, ensure
from app.modules.authorization.policy import Action
from app.modules.environments.models import DEFAULT_ENVIRONMENTS, Environment
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/api/orgs/{org_id}/projects", tags=["projects"])


async def get_org_project(
    session: AsyncSession, org_id: uuid.UUID, project_id: uuid.UUID
) -> Project:
    """Load a project only if it belongs to the given organization."""
    project = await session.scalar(
        select(Project).where(Project.id == project_id, Project.organization_id == org_id)
    )
    if project is None:
        raise not_found("project_not_found")
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(membership: MembershipDep, session: SessionDep):
    ensure(membership, Action.PROJECT_READ)
    projects = await session.scalars(
        select(Project)
        .where(Project.organization_id == membership.organization_id)
        .order_by(Project.name)
    )
    return list(projects)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, membership: MembershipDep, session: SessionDep):
    ensure(membership, Action.PROJECT_MANAGE)
    org_id = membership.organization_id

    async def taken(slug: str) -> bool:
        found = await session.scalar(
            select(Project.id).where(Project.organization_id == org_id, Project.slug == slug)
        )
        return found is not None

    if body.slug:
        if await taken(body.slug):
            raise conflict("slug_taken")
        slug = body.slug
    else:
        slug = await unique_slug(slugify(body.name, "project"), taken)

    project = Project(
        organization_id=org_id, name=body.name, slug=slug, description=body.description
    )
    session.add(project)
    await session.flush()
    for name, env_slug, protected in DEFAULT_ENVIRONMENTS:
        session.add(
            Environment(project_id=project.id, name=name, slug=env_slug, protected=protected)
        )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise conflict("slug_taken") from None
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, membership: MembershipDep, session: SessionDep):
    ensure(membership, Action.PROJECT_READ)
    return await get_org_project(session, membership.organization_id, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, membership: MembershipDep, session: SessionDep
):
    ensure(membership, Action.PROJECT_MANAGE)
    project = await get_org_project(session, membership.organization_id, project_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field in ("name", "slug") and value is None:
            continue
        setattr(project, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise conflict("slug_taken") from None
    await session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID, membership: MembershipDep, session: SessionDep
) -> None:
    ensure(membership, Action.PROJECT_MANAGE)
    project = await get_org_project(session, membership.organization_id, project_id)
    await session.delete(project)
    await session.commit()
