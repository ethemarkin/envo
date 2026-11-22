"""Resolving a service token from the Authorization header."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.deps import extract_token
from app.core.errors import unauthorized
from app.core.security import hash_token
from app.modules.groups.models import Group
from app.modules.projects.models import Project
from app.modules.service_tokens.models import TOKEN_PREFIX, ServiceToken

# Avoid a write on every CI request; minute precision is enough.
LAST_USED_GRANULARITY = timedelta(minutes=1)


@dataclass
class TokenAccess:
    """A request made with a service token, already matched to its project."""

    project: Project
    chain: list[Group]
    token: ServiceToken

    def allows_environment(self, environment_id: uuid.UUID) -> bool:
        return environment_id in self.token.environment_ids


def bearer_service_token(request: Request) -> str | None:
    token, via_cookie = extract_token(request)
    if token and not via_cookie and token.startswith(TOKEN_PREFIX):
        return token
    return None


async def resolve_service_token(session: AsyncSession, raw: str) -> ServiceToken:
    token = await session.scalar(
        select(ServiceToken).where(ServiceToken.token_hash == hash_token(raw))
    )
    now = utcnow()
    if (
        token is None
        or token.revoked_at is not None
        or (token.expires_at is not None and token.expires_at <= now)
    ):
        raise unauthorized("invalid_token")
    if token.last_used_at is None or now - token.last_used_at > LAST_USED_GRANULARITY:
        token.last_used_at = now
        await session.commit()
    return token
