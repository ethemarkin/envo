from typing import Annotated
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.deps import REFRESH_COOKIE, CurrentUser, SessionDep, check_csrf, get_optional_user
from app.core.errors import bad_request, conflict, not_found, unauthorized
from app.core.security import hash_password, hash_token, verify_password
from app.modules.audit_logs.service import record
from app.modules.auth import service
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.schemas import AuthConfigOut, LoginIn, SignupIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

oauth = OAuth()
_settings = get_settings()
if _settings.google_enabled:
    oauth.register(
        name="google",
        client_id=_settings.google_client_id,
        client_secret=_settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
    )


@router.get("/config", response_model=AuthConfigOut)
async def auth_config() -> AuthConfigOut:
    return AuthConfigOut(google_enabled=get_settings().google_enabled)


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupIn, request: Request, response: Response, session: SessionDep):
    user = User(email=body.email, name=body.name, password_hash=hash_password(body.password))
    user.identities = []
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise conflict("email_taken") from None
    await service.promote_if_first_user(session, user)
    record(session, request, "auth.signup", actor_user_id=user.id, details={"admin": user.is_admin})
    await service.issue_session(session, response, user, request.headers.get("user-agent"))
    return service.user_out(user)


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, request: Request, response: Response, session: SessionDep):
    user = await session.scalar(select(User).where(User.email == body.email))
    if not verify_password(body.password, user.password_hash if user else None):
        record(
            session,
            request,
            "auth.login_failed",
            actor_user_id=user.id if user else None,
            details={"email": body.email},
        )
        await session.commit()
        raise unauthorized("invalid_credentials")
    assert user is not None
    record(session, request, "auth.login", actor_user_id=user.id, details={"method": "password"})
    await service.issue_session(session, response, user, request.headers.get("user-agent"))
    return service.user_out(user)


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
async def refresh(request: Request, response: Response, session: SessionDep) -> Response:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise unauthorized("invalid_refresh_token")
    check_csrf(request)
    try:
        old = await service.rotate_refresh_token(session, raw)
    except service.RefreshError as e:
        failed = JSONResponse({"detail": e.code}, status_code=status.HTTP_401_UNAUTHORIZED)
        service.clear_auth_cookies(failed)
        return failed
    user = await session.get(User, old.user_id)
    assert user is not None
    await service.issue_session(
        session, response, user, request.headers.get("user-agent"), family_id=old.family_id
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, session: SessionDep) -> Response:
    check_csrf(request)
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        token = await session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
        )
        if token is not None:
            await service.revoke_family(session, token.family_id)
            await session.commit()
    service.clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: CurrentUser, response: Response, session: SessionDep) -> Response:
    """Revoke every refresh token of the user. Access tokens expire on their own
    within the access token TTL."""
    await service.revoke_all_for_user(session, user.id)
    await session.commit()
    service.clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return service.user_out(user)


@router.delete("/identities/{provider}", response_model=UserOut)
async def unlink_identity(provider: str, user: CurrentUser, session: SessionDep) -> UserOut:
    identity = next((i for i in user.identities if i.provider == provider), None)
    if identity is None:
        raise not_found("identity_not_found")
    if user.password_hash is None and len(user.identities) == 1:
        raise bad_request("last_login_method")
    await session.delete(identity)
    await session.commit()
    await session.refresh(user, ["identities"])
    return service.user_out(user)


# --- Google OpenID Connect -------------------------------------------------


def _frontend_redirect(path: str, **params: str) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{get_settings().frontend_url}{path}{query}", status_code=302)


@router.get("/google/start")
async def google_start(
    request: Request,
    user: Annotated[User | None, Depends(get_optional_user)],
    link: bool = False,
):
    if not get_settings().google_enabled:
        raise not_found("google_disabled")
    if link and user is None:
        raise unauthorized()
    request.session["google_link"] = link
    redirect_uri = f"{get_settings().api_url}/api/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    session: SessionDep,
    user: Annotated[User | None, Depends(get_optional_user)],
):
    if not get_settings().google_enabled:
        raise not_found("google_disabled")
    link = bool(request.session.pop("google_link", False))
    error_path = "/settings" if link else "/login"
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return _frontend_redirect(error_path, error="google_failed")
    claims = token.get("userinfo") or {}
    if link and user is None:
        return _frontend_redirect("/login", error="session_expired")
    try:
        resolved = await service.resolve_google_login(
            session,
            subject=str(claims["sub"]),
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified")),
            name=claims.get("name"),
            current_user=user if link else None,
        )
    except service.GoogleLoginError as e:
        return _frontend_redirect(error_path, error=e.code)
    except IntegrityError:
        await session.rollback()
        return _frontend_redirect(error_path, error="identity_linked_elsewhere")

    if link:
        return _frontend_redirect("/settings", linked="google")
    response = _frontend_redirect("/")
    record(session, request, "auth.login", actor_user_id=resolved.id, details={"method": "google"})
    await service.issue_session(session, response, resolved, request.headers.get("user-agent"))
    return response
