import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import SessionDep
from app.core.errors import conflict, not_found
from app.core.slugs import slugify
from app.modules.audit_logs.service import record
from app.modules.authorization.deps import MembershipDep, ensure
from app.modules.authorization.policy import Action
from app.modules.environments.models import Environment
from app.modules.environments.schemas import EnvironmentCreate, EnvironmentOut, EnvironmentUpdate
from app.modules.projects.router import get_org_project

router = APIRouter(
    prefix="/api/orgs/{org_id}/projects/{project_id}/environments", tags=["environments"]
)


def _audit(session, request, membership, action: str, env: Environment, **details) -> None:
    record(
        session,
        request,
        action,
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        resource_type="environment",
        resource_id=env.id,
        details={"project_id": str(env.project_id), "slug": env.slug, **details},
    )


async def get_project_environment(
    session: AsyncSession, project_id: uuid.UUID, env_id: uuid.UUID
) -> Environment:
    env = await session.scalar(
        select(Environment).where(Environment.id == env_id, Environment.project_id == project_id)
    )
    if env is None:
        raise not_found("environment_not_found")
    return env


@router.get("", response_model=list[EnvironmentOut])
async def list_environments(project_id: uuid.UUID, membership: MembershipDep, session: SessionDep):
    ensure(membership, Action.ENVIRONMENT_READ)
    project = await get_org_project(session, membership.organization_id, project_id)
    envs = await session.scalars(
        select(Environment)
        .where(Environment.project_id == project.id)
        .order_by(Environment.created_at)
    )
    return list(envs)


@router.post("", response_model=EnvironmentOut, status_code=status.HTTP_201_CREATED)
async def create_environment(
    project_id: uuid.UUID,
    body: EnvironmentCreate,
    membership: MembershipDep,
    request: Request,
    session: SessionDep,
):
    ensure(membership, Action.ENVIRONMENT_MANAGE)
    project = await get_org_project(session, membership.organization_id, project_id)
    env = Environment(
        project_id=project.id,
        name=body.name,
        slug=body.slug or slugify(body.name, "env"),
        protected=body.protected,
    )
    session.add(env)
    try:
        await session.flush()
        _audit(session, request, membership, "environment.created", env, protected=env.protected)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise conflict("slug_taken") from None
    return env


@router.patch("/{env_id}", response_model=EnvironmentOut)
async def update_environment(
    project_id: uuid.UUID,
    env_id: uuid.UUID,
    body: EnvironmentUpdate,
    membership: MembershipDep,
    request: Request,
    session: SessionDep,
):
    ensure(membership, Action.ENVIRONMENT_MANAGE)
    project = await get_org_project(session, membership.organization_id, project_id)
    env = await get_project_environment(session, project.id, env_id)
    changes = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None and getattr(env, field) != value:
            changes[field] = {"from": getattr(env, field), "to": value}
            setattr(env, field, value)
    if changes:
        _audit(session, request, membership, "environment.updated", env, changes=changes)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise conflict("slug_taken") from None
    await session.refresh(env)
    return env


@router.delete("/{env_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_environment(
    project_id: uuid.UUID,
    env_id: uuid.UUID,
    membership: MembershipDep,
    request: Request,
    session: SessionDep,
) -> None:
    ensure(membership, Action.ENVIRONMENT_MANAGE)
    project = await get_org_project(session, membership.organization_id, project_id)
    env = await get_project_environment(session, project.id, env_id)
    _audit(session, request, membership, "environment.deleted", env)
    await session.delete(env)
    await session.commit()
