import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.db import utcnow
from app.core.deps import SessionDep
from app.core.errors import bad_request, not_found, unauthorized
from app.core.security import hash_token
from app.modules.audit_logs.service import record
from app.modules.auth.models import User
from app.modules.authorization.access import ancestor_chain, path_of
from app.modules.authorization.deps import ProjectAccessDep
from app.modules.authorization.policy import Action
from app.modules.environments.models import Environment
from app.modules.projects.models import Project
from app.modules.service_tokens.auth import bearer_service_token, resolve_service_token
from app.modules.service_tokens.models import (
    TOKEN_PREFIX,
    ServiceToken,
    ServiceTokenEnvironment,
)

router = APIRouter(tags=["service-tokens"])


class TokenEnvironmentOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class ServiceTokenOut(BaseModel):
    id: uuid.UUID
    name: str
    # Shown as "envo_st_<hint>…" so tokens can be told apart.
    hint: str
    can_write: bool
    environments: list[TokenEnvironmentOut]
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    created_by: str | None


class ServiceTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    environment_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    can_write: bool = False
    # None: no expiry. Prefer a limit; CI secrets leak.
    expires_in_days: int | None = Field(default=90, ge=1, le=3650)


class ServiceTokenCreated(BaseModel):
    # The plain token, shown exactly once.
    token: str
    service_token: ServiceTokenOut


class ServiceTokenSelf(BaseModel):
    name: str
    project_id: uuid.UUID
    project_path: str
    can_write: bool
    environments: list[TokenEnvironmentOut]
    expires_at: datetime | None


async def _environments(session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Environment]:
    if not ids:
        return {}
    rows = await session.scalars(select(Environment).where(Environment.id.in_(ids)))
    return {e.id: e for e in rows}


def _token_out(
    t: ServiceToken, envs: dict[uuid.UUID, Environment], creators: dict[uuid.UUID, User]
) -> ServiceTokenOut:
    creator = creators.get(t.created_by_id) if t.created_by_id else None
    return ServiceTokenOut(
        id=t.id,
        name=t.name,
        hint=t.hint,
        can_write=t.can_write,
        environments=[
            TokenEnvironmentOut(id=e.id, name=e.name, slug=e.slug)
            for e in sorted((envs[i] for i in t.environment_ids if i in envs), key=lambda e: e.slug)
        ],
        expires_at=t.expires_at,
        revoked_at=t.revoked_at,
        last_used_at=t.last_used_at,
        created_at=t.created_at,
        created_by=(creator.name or creator.email) if creator else None,
    )


@router.get("/api/projects/{project_id}/service-tokens", response_model=list[ServiceTokenOut])
async def list_tokens(access: ProjectAccessDep, session: SessionDep):
    access.ensure(Action.SERVICE_TOKEN_MANAGE)
    tokens = list(
        await session.scalars(
            select(ServiceToken)
            .where(ServiceToken.project_id == access.project.id)
            .order_by(ServiceToken.created_at.desc())
        )
    )
    envs = await _environments(session, {i for t in tokens for i in t.environment_ids})
    creator_ids = {t.created_by_id for t in tokens if t.created_by_id}
    creators = (
        {u.id: u for u in await session.scalars(select(User).where(User.id.in_(creator_ids)))}
        if creator_ids
        else {}
    )
    return [_token_out(t, envs, creators) for t in tokens]


@router.post(
    "/api/projects/{project_id}/service-tokens",
    response_model=ServiceTokenCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_token(
    body: ServiceTokenCreate, access: ProjectAccessDep, request: Request, session: SessionDep
):
    access.ensure(Action.SERVICE_TOKEN_MANAGE)
    wanted = set(body.environment_ids)
    envs = await _environments(session, wanted)
    if set(envs) != wanted or any(e.project_id != access.project.id for e in envs.values()):
        raise bad_request("invalid_environment")

    secret = secrets.token_urlsafe(32)
    raw = TOKEN_PREFIX + secret
    token = ServiceToken(
        project_id=access.project.id,
        name=body.name,
        token_hash=hash_token(raw),
        hint=secret[:6],
        can_write=body.can_write,
        expires_at=utcnow() + timedelta(days=body.expires_in_days)
        if body.expires_in_days
        else None,
        created_by_id=access.user.id,
    )
    token.environments = [ServiceTokenEnvironment(environment_id=i) for i in wanted]
    session.add(token)
    await session.flush()
    record(
        session,
        request,
        "service_token.created",
        actor_user_id=access.user.id,
        project_id=access.project.id,
        group_id=access.project.group_id,
        resource_type="service_token",
        resource_id=token.id,
        details={
            "name": body.name,
            "environments": sorted(e.slug for e in envs.values()),
            "can_write": body.can_write,
            "expires_in_days": body.expires_in_days,
        },
    )
    await session.commit()
    await session.refresh(token, ["environments"])
    return ServiceTokenCreated(
        token=raw, service_token=_token_out(token, envs, {access.user.id: access.user})
    )


@router.delete(
    "/api/projects/{project_id}/service-tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_token(
    token_id: uuid.UUID, access: ProjectAccessDep, request: Request, session: SessionDep
) -> None:
    access.ensure(Action.SERVICE_TOKEN_MANAGE)
    token = await session.scalar(
        select(ServiceToken).where(
            ServiceToken.id == token_id, ServiceToken.project_id == access.project.id
        )
    )
    if token is None:
        raise not_found("service_token_not_found")
    if token.revoked_at is None:
        token.revoked_at = utcnow()
        record(
            session,
            request,
            "service_token.revoked",
            actor_user_id=access.user.id,
            project_id=access.project.id,
            group_id=access.project.group_id,
            resource_type="service_token",
            resource_id=token.id,
            details={"name": token.name},
        )
        await session.commit()


@router.get("/api/service-tokens/self", response_model=ServiceTokenSelf)
async def token_self(request: Request, session: SessionDep):
    """What the presented service token can do (`envo whoami` in CI)."""
    raw = bearer_service_token(request)
    if raw is None:
        raise unauthorized("invalid_token")
    token = await resolve_service_token(session, raw)
    project = await session.get(Project, token.project_id)
    assert project is not None
    chain = await ancestor_chain(session, project.group_id)
    envs = await _environments(session, token.environment_ids)
    return ServiceTokenSelf(
        name=token.name,
        project_id=project.id,
        project_path=path_of(chain, project.slug),
        can_write=token.can_write,
        environments=[
            TokenEnvironmentOut(id=e.id, name=e.name, slug=e.slug)
            for e in sorted(envs.values(), key=lambda e: e.slug)
        ],
        expires_at=token.expires_at,
    )
