from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import REFRESH_COOKIE, CurrentUser, SessionDep, check_csrf
from app.core.errors import conflict, forbidden, unauthorized
from app.core.security import hash_password, hash_token, verify_password
from app.modules.audit_logs.service import record
from app.modules.auth import service
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.schemas import LoginIn, RegistrationOut, SignupIn, UserOut
from app.modules.groups import invitations

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/registration", response_model=RegistrationOut)
async def registration(session: SessionDep) -> RegistrationOut:
    return RegistrationOut(invitation_required=not await service.instance_is_empty(session))


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupIn, request: Request, response: Response, session: SessionDep):
    """Accounts are created by invitation only. The exception is the first
    account of an instance, which becomes its administrator."""
    inv = None
    if body.invite_token:
        inv = await invitations.load_pending(session, body.invite_token, lock=True)
        if inv.email != body.email:
            raise forbidden("invitation_email_mismatch")
    elif not await service.instance_is_empty(session, lock=True):
        raise forbidden("invitation_required")

    user = User(email=body.email, name=body.name, password_hash=hash_password(body.password))
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise conflict("email_taken") from None
    await service.promote_if_first_user(session, user)
    record(
        session,
        request,
        "auth.signup",
        actor_user_id=user.id,
        details={"admin": user.is_admin, "invitation_id": str(inv.id) if inv else None},
    )
    if inv is not None:
        await invitations.redeem(session, request, inv, user)
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
