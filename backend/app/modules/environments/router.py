import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import SessionDep
from app.core.errors import conflict, not_found
from app.core.slugs import slugify
from app.modules.audit_logs.service import record
from app.modules.authorization.deps import ProjectAccess, ProjectAccessDep, ProjectActorDep
from app.modules.authorization.policy import Action
from app.modules.environments.models import Environment
from app.modules.environments.schemas import EnvironmentCreate, EnvironmentOut, EnvironmentUpdate
from app.modules.service_tokens.auth import TokenAccess

router = APIRouter(prefix="/api/projects/{project_id}/environments", tags=["environments"])


def _audit(session, request, access: ProjectAccess, action: str, env: Environment, **details):
    record(
        session,
        request,
        action,
        actor_user_id=access.user.id,
        project_id=access.project.id,
        group_id=access.project.group_id,
        resource_type="environment",
        resource_id=env.id,
        details={"slug": env.slug, **details},
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
async def list_environments(access: ProjectActorDep, session: SessionDep):
    """Service tokens see only the environments in their scope."""
    query = (
        select(Environment)
        .where(Environment.project_id == access.project.id)
        .order_by(Environment.created_at)
    )
    if isinstance(access, TokenAccess):
        query = query.where(Environment.id.in_(access.token.environment_ids))
    else:
        access.ensure(Action.READ)
    return list(await session.scalars(query))


@router.post("", response_model=EnvironmentOut, status_code=status.HTTP_201_CREATED)
async def create_environment(
    body: EnvironmentCreate, access: ProjectAccessDep, request: Request, session: SessionDep
):
    access.ensure(Action.ENVIRONMENT_MANAGE)
    env = Environment(
        project_id=access.project.id,
        name=body.name,
        slug=body.slug or slugify(body.name, "env"),
        protected=body.protected,
    )
    session.add(env)
    try:
        await session.flush()
        _audit(session, request, access, "environment.created", env, protected=env.protected)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise conflict("slug_taken") from None
    return env


@router.patch("/{env_id}", response_model=EnvironmentOut)
async def update_environment(
    env_id: uuid.UUID,
    body: EnvironmentUpdate,
    access: ProjectAccessDep,
    request: Request,
    session: SessionDep,
):
    access.ensure(Action.ENVIRONMENT_MANAGE)
    env = await get_project_environment(session, access.project.id, env_id)
    changes = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None and getattr(env, field) != value:
            changes[field] = {"from": getattr(env, field), "to": value}
            setattr(env, field, value)
    if changes:
        _audit(session, request, access, "environment.updated", env, changes=changes)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise conflict("slug_taken") from None
    await session.refresh(env)
    return env


@router.delete("/{env_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_environment(
    env_id: uuid.UUID, access: ProjectAccessDep, request: Request, session: SessionDep
) -> None:
    access.ensure(Action.ENVIRONMENT_MANAGE)
    env = await get_project_environment(session, access.project.id, env_id)
    _audit(session, request, access, "environment.deleted", env)
    await session.delete(env)
    await session.commit()
