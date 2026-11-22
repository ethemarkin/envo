from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.crypto.keys import KeyConfigError
from app.core.frontend import mount_frontend
from app.modules.admin.router import router as admin_router
from app.modules.audit_logs.router import router as audit_router
from app.modules.auth.cli_router import router as cli_auth_router
from app.modules.auth.router import router as auth_router
from app.modules.environments.router import router as environments_router
from app.modules.groups.invitation_router import router as invitation_router
from app.modules.groups.router import router as groups_router
from app.modules.groups.tree_router import router as tree_router
from app.modules.projects.router import router as projects_router
from app.modules.service_tokens.router import router as service_tokens_router
from app.modules.variables.router import router as variables_router
from app.modules.versions.router import router as versions_router


def create_app(static_dir: str | None = None) -> FastAPI:
    settings = get_settings()  # also fails fast on invalid configuration
    app = FastAPI(
        title="Envo API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(cli_auth_router)
    app.include_router(tree_router)
    app.include_router(groups_router)
    app.include_router(invitation_router)
    app.include_router(projects_router)
    app.include_router(environments_router)
    app.include_router(variables_router)
    app.include_router(versions_router)
    app.include_router(service_tokens_router)
    app.include_router(admin_router)
    app.include_router(audit_router)

    @app.exception_handler(KeyConfigError)
    async def key_config_error(request: Request, exc: KeyConfigError) -> JSONResponse:
        # Misconfigured master key: fail closed with a clear code, no details.
        return JSONResponse({"detail": "encryption_not_configured"}, status_code=503)

    # Last: the dashboard's catch-all route must not shadow API routes.
    mount_frontend(app, static_dir or settings.static_dir)
    return app


app = create_app()
