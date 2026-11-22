from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.core.crypto.keys import KeyConfigError
from app.modules.auth.router import router as auth_router
from app.modules.environments.router import router as environments_router
from app.modules.organizations.router import router as organizations_router
from app.modules.projects.router import router as projects_router
from app.modules.variables.router import router as variables_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Envo API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    # Short-lived signed cookie that only carries OAuth state/PKCE/nonce
    # between /google/start and /google/callback.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="envo_oauth",
        max_age=600,
        path="/api/auth",
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(organizations_router)
    app.include_router(projects_router)
    app.include_router(environments_router)
    app.include_router(variables_router)

    @app.exception_handler(KeyConfigError)
    async def key_config_error(request: Request, exc: KeyConfigError) -> JSONResponse:
        # Misconfigured master key: fail closed with a clear code, no details.
        return JSONResponse({"detail": "encryption_not_configured"}, status_code=503)

    return app


app = create_app()
