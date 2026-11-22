"""`envo login`: browser-approved CLI sign-in (OAuth device flow style).

1. The CLI calls /start and gets a secret device code plus a short user code.
2. The user opens the verification page in a browser where they are signed in,
   types the user code shown in the terminal and approves the request.
   The code is never part of the link, so a link alone cannot be used to make
   someone approve a request they did not start.
3. The CLI polls /token with the device code and receives an access token and
   a rotating refresh token. Tokens are returned in the body; no cookies.
"""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.deps import CurrentUser, SessionDep
from app.core.errors import not_found, unauthorized
from app.core.security import create_access_token, hash_token, new_opaque_token
from app.modules.audit_logs.service import record
from app.modules.auth import service
from app.modules.auth.cli_models import CliLoginRequest, CliLoginStatus
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.schemas import UserOut

router = APIRouter(prefix="/api/cli/auth", tags=["cli-auth"])

REQUEST_TTL = timedelta(minutes=10)
POLL_INTERVAL_SECONDS = 2
# No vowels or look-alike characters: codes are read aloud and typed by hand.
USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"


def new_user_code() -> str:
    raw = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_user_code(code: str) -> str:
    raw = "".join(c for c in code.upper() if c.isalnum())
    return f"{raw[:4]}-{raw[4:]}" if len(raw) == 8 else raw


def is_expired(req: CliLoginRequest) -> bool:
    expires = req.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= datetime.now(UTC)


class StartIn(BaseModel):
    client_name: str | None = Field(default=None, max_length=200)


class StartOut(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class UserCodeIn(BaseModel):
    user_code: str = Field(max_length=32)


class RequestOut(BaseModel):
    user_code: str
    client_name: str | None
    client_ip: str | None
    created_at: datetime
    expires_at: datetime


class DeviceCodeIn(BaseModel):
    device_code: str = Field(max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=200)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"  # noqa: S105 (the OAuth token type name)
    expires_in: int
    user: UserOut


def oauth_error(code: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> JSONResponse:
    return JSONResponse({"detail": code}, status_code=status_code)


def token_out(user: User, refresh_token: str) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id),
        refresh_token=refresh_token,
        expires_in=get_settings().access_token_ttl_seconds,
        user=service.user_out(user),
    )


@router.post("/start", response_model=StartOut)
async def start(body: StartIn, request: Request, session: SessionDep) -> StartOut:
    device_code = new_opaque_token()
    user_code = new_user_code()
    while await session.scalar(
        select(CliLoginRequest.id).where(CliLoginRequest.user_code == user_code)
    ):
        user_code = new_user_code()
    session.add(
        CliLoginRequest(
            device_code_hash=hash_token(device_code),
            user_code=user_code,
            client_name=body.client_name,
            client_ip=request.client.host if request.client else None,
            expires_at=utcnow() + REQUEST_TTL,
        )
    )
    await session.commit()
    return StartOut(
        device_code=device_code,
        user_code=user_code,
        verification_uri=f"{get_settings().frontend_url}/cli/authorize",
        expires_in=int(REQUEST_TTL.total_seconds()),
        interval=POLL_INTERVAL_SECONDS,
    )


async def _pending_request(session: SessionDep, user_code: str) -> CliLoginRequest:
    req = await session.scalar(
        select(CliLoginRequest)
        .where(CliLoginRequest.user_code == normalize_user_code(user_code))
        .with_for_update()
    )
    if req is None or req.status != CliLoginStatus.PENDING or is_expired(req):
        raise not_found("cli_request_not_found")
    return req


@router.get("/requests/{user_code}", response_model=RequestOut)
async def get_request(user_code: str, user: CurrentUser, session: SessionDep) -> RequestOut:
    req = await _pending_request(session, user_code)
    return RequestOut(
        user_code=req.user_code,
        client_name=req.client_name,
        client_ip=req.client_ip,
        created_at=req.created_at,
        expires_at=req.expires_at,
    )


@router.post("/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve(
    body: UserCodeIn, user: CurrentUser, request: Request, session: SessionDep
) -> None:
    req = await _pending_request(session, body.user_code)
    req.status = CliLoginStatus.APPROVED
    req.user_id = user.id
    record(
        session,
        request,
        "auth.cli_login_approved",
        actor_user_id=user.id,
        details={"client_name": req.client_name, "client_ip": req.client_ip},
    )
    await session.commit()


@router.post("/deny", status_code=status.HTTP_204_NO_CONTENT)
async def deny(body: UserCodeIn, user: CurrentUser, session: SessionDep) -> None:
    req = await _pending_request(session, body.user_code)
    req.status = CliLoginStatus.DENIED
    await session.commit()


@router.post("/token", response_model=TokenOut)
async def token(body: DeviceCodeIn, request: Request, session: SessionDep):
    req = await session.scalar(
        select(CliLoginRequest)
        .where(CliLoginRequest.device_code_hash == hash_token(body.device_code))
        .with_for_update()
    )
    if req is None or req.status == CliLoginStatus.CONSUMED:
        return oauth_error("invalid_grant")
    if is_expired(req):
        return oauth_error("expired_token")
    if req.status == CliLoginStatus.DENIED:
        return oauth_error("access_denied")
    if req.status == CliLoginStatus.PENDING:
        return oauth_error("authorization_pending")

    user = await session.get(User, req.user_id)
    if user is None:
        return oauth_error("invalid_grant")
    req.status = CliLoginStatus.CONSUMED
    agent = f"envo-cli ({req.client_name})" if req.client_name else "envo-cli"
    raw = service.add_refresh_token(session, user, agent)
    record(session, request, "auth.login", actor_user_id=user.id, details={"method": "cli"})
    await session.commit()
    return token_out(user, raw)


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, session: SessionDep):
    try:
        old = await service.rotate_refresh_token(session, body.refresh_token)
    except service.RefreshError as e:
        return oauth_error(e.code, status.HTTP_401_UNAUTHORIZED)
    user = await session.get(User, old.user_id)
    if user is None:
        raise unauthorized("invalid_refresh_token")
    raw = service.add_refresh_token(session, user, old.user_agent, family_id=old.family_id)
    await session.commit()
    return token_out(user, raw)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshIn, session: SessionDep) -> None:
    token_row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token))
    )
    if token_row is not None:
        await service.revoke_family(session, token_row.family_id)
        await session.commit()
