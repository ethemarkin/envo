"""Who did something: a user or a service token, as a display label."""

import uuid
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.service_tokens.models import ServiceToken


class ActorOut(BaseModel):
    type: Literal["user", "token", "unknown"]
    id: uuid.UUID | None
    label: str


class ActorLabels:
    def __init__(self, users: dict[uuid.UUID, str], tokens: dict[uuid.UUID, str]) -> None:
        self.users, self.tokens = users, tokens

    @classmethod
    async def load(
        cls, session: AsyncSession, user_ids: set[uuid.UUID], token_ids: set[uuid.UUID]
    ) -> "ActorLabels":
        users: dict[uuid.UUID, str] = {}
        tokens: dict[uuid.UUID, str] = {}
        if user_ids:
            for u in await session.scalars(select(User).where(User.id.in_(user_ids))):
                users[u.id] = u.name or u.email
        if token_ids:
            for t in await session.scalars(
                select(ServiceToken).where(ServiceToken.id.in_(token_ids))
            ):
                tokens[t.id] = t.name
        return cls(users, tokens)

    def actor(self, user_id: uuid.UUID | None, token_id: uuid.UUID | None) -> ActorOut:
        if token_id is not None:
            return ActorOut(
                type="token", id=token_id, label=self.tokens.get(token_id, "silinmiş token")
            )
        if user_id is not None:
            return ActorOut(
                type="user", id=user_id, label=self.users.get(user_id, "silinmiş kullanıcı")
            )
        return ActorOut(type="unknown", id=None, label="anonim")
