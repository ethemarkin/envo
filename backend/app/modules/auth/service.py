import uuid
from datetime import timedelta

from fastapi import Response
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.deps import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
from app.core.security import create_access_token, hash_token, new_opaque_token
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.schemas import UserOut

ACCESS_COOKIE_PATH = "/api"
REFRESH_COOKIE_PATH = "/api/auth"
# A refresh token rotated this recently may be presented again without being
# treated as theft: two tabs often refresh at the same moment.
ROTATION_GRACE = timedelta(seconds=30)


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        email_verified=user.email_verified,
        is_admin=user.is_admin,
    )


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    s = get_settings()
    common = {"secure": s.cookie_secure, "samesite": "lax", "domain": s.cookie_domain}
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=s.access_token_ttl_seconds,
        path=ACCESS_COOKIE_PATH,
        httponly=True,
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=s.refresh_token_ttl_seconds,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        **common,
    )
    # Readable by the SPA so it can echo the value in the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE,
        new_opaque_token(),
        max_age=s.refresh_token_ttl_seconds,
        path="/",
        httponly=False,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    s = get_settings()
    for name, path in (
        (ACCESS_COOKIE, ACCESS_COOKIE_PATH),
        (REFRESH_COOKIE, REFRESH_COOKIE_PATH),
        (CSRF_COOKIE, "/"),
    ):
        response.delete_cookie(name, path=path, domain=s.cookie_domain)


async def issue_session(
    session: AsyncSession,
    response: Response,
    user: User,
    user_agent: str | None,
    family_id: uuid.UUID | None = None,
) -> None:
    """Browser session: tokens go into HttpOnly cookies."""
    raw = add_refresh_token(session, user, user_agent, family_id)
    await session.commit()
    set_auth_cookies(response, create_access_token(user.id), raw)


def add_refresh_token(
    session: AsyncSession,
    user: User,
    user_agent: str | None,
    family_id: uuid.UUID | None = None,
) -> str:
    """Add a new refresh token row to the session and return the raw token."""
    raw = new_opaque_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id or uuid.uuid4(),
            token_hash=hash_token(raw),
            expires_at=utcnow() + timedelta(seconds=get_settings().refresh_token_ttl_seconds),
            user_agent=(user_agent or "")[:500] or None,
        )
    )
    return raw


async def promote_if_first_user(session: AsyncSession, user: User) -> None:
    """The first account of an instance becomes its administrator.

    Must run after the user row is flushed, in the same transaction. The
    advisory lock serializes concurrent first sign-ups.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('envo:first-user'))"))
    count = await session.scalar(select(func.count()).select_from(User))
    if count == 1:
        user.is_admin = True


class RefreshError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


async def rotate_refresh_token(session: AsyncSession, raw: str) -> RefreshToken:
    """Validate and mark a refresh token as rotated. Returns the old row; the
    caller issues the next token in the same family."""
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)).with_for_update()
    )
    now = utcnow()
    if token is None or token.revoked_at is not None or token.expires_at <= now:
        raise RefreshError("invalid_refresh_token")
    if token.rotated_at is not None:
        if now - token.rotated_at > ROTATION_GRACE:
            await revoke_family(session, token.family_id)
            await session.commit()
            raise RefreshError("refresh_token_reused")
        return token
    token.rotated_at = now
    return token


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
