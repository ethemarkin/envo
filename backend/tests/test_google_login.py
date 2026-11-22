"""Account resolution for Google sign-in (the OAuth redirect itself is Authlib's)."""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.auth.models import User
from app.modules.auth.service import GoogleLoginError, resolve_google_login


async def resolve(current_user_id: str | None = None, **overrides):
    params = {
        "subject": "google-sub-1",
        "email": "g@example.com",
        "email_verified": True,
        "name": "G User",
    } | overrides
    async with SessionLocal() as session:
        # Like the router: the signed-in user comes from the same DB session.
        current = await session.get(User, uuid.UUID(current_user_id)) if current_user_id else None
        return await resolve_google_login(session, current_user=current, **params)


async def test_creates_new_user_without_password():
    user = await resolve()
    assert user.email == "g@example.com"
    assert user.password_hash is None
    assert user.email_verified is True
    assert [i.provider for i in user.identities] == ["google"]


async def test_known_identity_signs_in_same_user():
    first = await resolve()
    second = await resolve(email="changed@example.com")
    assert second.id == first.id


async def test_unverified_email_is_rejected():
    with pytest.raises(GoogleLoginError) as e:
        await resolve(email_verified=False)
    assert e.value.code == "email_not_verified"


async def test_existing_email_is_not_merged_silently(new_user):
    await new_user("taken@example.com")
    with pytest.raises(GoogleLoginError) as e:
        await resolve(email="taken@example.com")
    assert e.value.code == "account_exists"
    async with SessionLocal() as session:
        users = (await session.scalars(select(User).where(User.email == "taken@example.com"))).all()
        assert len(users) == 1 and users[0].identities == []


async def test_signed_in_user_can_link_google(new_user):
    _, me = await new_user("me@example.com")
    linked = await resolve(email="other-address@gmail.com", current_user_id=me["id"])
    assert str(linked.id) == me["id"]
    assert [i.provider for i in linked.identities] == ["google"]


async def test_identity_linked_to_another_user_cannot_be_linked_again(new_user):
    await resolve(subject="shared-sub", email="owner@example.com")
    _, me = await new_user("me@example.com")
    with pytest.raises(GoogleLoginError) as e:
        await resolve(subject="shared-sub", current_user_id=me["id"])
    assert e.value.code == "identity_linked_elsewhere"
