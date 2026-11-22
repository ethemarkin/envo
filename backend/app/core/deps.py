"""Request authentication.

Browsers authenticate with HttpOnly cookies; every state-changing cookie
request must also carry the double-submit CSRF header. The CLI and service
tokens use the Authorization header, which is not sent automatically by
browsers and therefore needs no CSRF check.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import forbidden, unauthorized
from app.core.security import decode_access_token
from app.modules.auth.models import User
from app.modules.service_tokens.models import TOKEN_PREFIX

ACCESS_COOKIE = "envo_access"
REFRESH_COOKIE = "envo_refresh"
CSRF_COOKIE = "envo_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def check_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise forbidden("csrf_failed")


def extract_token(request: Request) -> tuple[str | None, bool]:
    auth = request.headers.get("Authorization")
    if auth:
        scheme, _, value = auth.partition(" ")
        if scheme.lower() == "bearer" and value:
            return value, False
        return None, False
    return request.cookies.get(ACCESS_COOKIE), True


async def get_optional_user(request: Request, session: SessionDep) -> User | None:
    token, via_cookie = extract_token(request)
    if not token:
        return None
    if token.startswith(TOKEN_PREFIX):
        # Service tokens are not users; only the routes that accept them
        # (environments and variables of their project) resolve them.
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    if via_cookie:
        check_csrf(request)
    # "web" for browser cookies, "cli" for bearer tokens; recorded in history.
    request.state.auth_method = "web" if via_cookie else "cli"
    return await session.get(User, user_id)


async def get_current_user(
    request: Request,
    user: Annotated[User | None, Depends(get_optional_user)],
) -> User:
    if user is None:
        token, via_cookie = extract_token(request)
        if token and not via_cookie and token.startswith(TOKEN_PREFIX):
            raise forbidden("service_token_not_allowed")
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
