import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import bad_request, forbidden
from app.modules.audit_logs.service import record
from app.modules.authorization.deps import MembershipDep
from app.modules.authorization.policy import EnvAction, can_env
from app.modules.environments.models import Environment
from app.modules.environments.router import get_project_environment
from app.modules.organizations.models import Membership
from app.modules.projects.models import Project
from app.modules.projects.router import get_org_project
from app.modules.variables import dotenv
from app.modules.variables.models import Visibility
from app.modules.variables.schemas import (
    BatchIn,
    ImportIn,
    ImportItem,
    ImportOut,
    RevealIn,
    RevealOut,
    SingleSetIn,
    VariableListOut,
    VariableOut,
    WriteOut,
)
from app.modules.variables.service import (
    DEFAULT_VISIBILITY,
    SetOp,
    VariableError,
    apply_changes,
    decrypt_all,
    load_variables,
)
from app.modules.versions.models import ChangeAction, ChangeSource

router = APIRouter(
    prefix="/api/orgs/{org_id}/projects/{project_id}/environments/{env_id}",
    tags=["variables"],
)

NO_STORE = {"Cache-Control": "no-store"}


@dataclass
class EnvContext:
    membership: Membership
    project: Project
    env: Environment
    user_id: uuid.UUID
    source: ChangeSource

    def allowed(self, action: EnvAction) -> bool:
        return can_env(self.membership.role, action, self.env.protected)

    def require(self, action: EnvAction) -> None:
        if not self.allowed(action):
            raise forbidden()


async def env_context(
    project_id: uuid.UUID,
    env_id: uuid.UUID,
    request: Request,
    membership: MembershipDep,
    user: CurrentUser,
    session: SessionDep,
) -> EnvContext:
    project = await get_org_project(session, membership.organization_id, project_id)
    env = await get_project_environment(session, project.id, env_id)
    method = getattr(request.state, "auth_method", "web")
    return EnvContext(membership, project, env, user.id, ChangeSource(method))


Ctx = Annotated[EnvContext, Depends(env_context)]


def error_response(e: VariableError) -> JSONResponse:
    return JSONResponse({"detail": e.code, "keys": e.keys}, status_code=e.status)


def parse_if_match(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip().removeprefix("W/").strip('"'))
    except ValueError:
        raise bad_request("invalid_if_match") from None


def write_out(result) -> WriteOut:
    return WriteOut(
        revision=result.revision,
        created=result.keys(ChangeAction.CREATE),
        updated=result.keys(ChangeAction.UPDATE),
        deleted=result.keys(ChangeAction.DELETE),
    )


@router.get("/variables", response_model=VariableListOut)
async def list_variables(ctx: Ctx, session: SessionDep):
    ctx.require(EnvAction.LIST)
    variables = await load_variables(session, ctx.env.id)
    visible = [v for v in variables if v.visibility == Visibility.VISIBLE]
    plaintext = decrypt_all(ctx.env, visible)
    body = VariableListOut(
        revision=ctx.env.revision,
        protected=ctx.env.protected,
        can_read_secrets=ctx.allowed(EnvAction.READ_SECRETS),
        can_write=ctx.allowed(EnvAction.WRITE),
        variables=[
            VariableOut(
                key=v.key,
                visibility=v.visibility,
                value=plaintext.get(v.key),
                updated_at=v.updated_at,
            )
            for v in variables
        ],
    )
    return JSONResponse(
        body.model_dump(mode="json"), headers={"ETag": f'"{ctx.env.revision}"', **NO_STORE}
    )


@router.post("/variables/reveal", response_model=RevealOut)
async def reveal_variables(body: RevealIn, ctx: Ctx, request: Request, session: SessionDep):
    ctx.require(EnvAction.READ_SECRETS)
    variables = await load_variables(session, ctx.env.id)
    if body.keys is not None:
        wanted = set(body.keys)
        variables = [v for v in variables if v.key in wanted]
    else:
        variables = [v for v in variables if v.visibility == Visibility.SECRET]
    values = decrypt_all(ctx.env, variables)
    record(
        session,
        request,
        "variables.revealed",
        actor_user_id=ctx.user_id,
        organization_id=ctx.membership.organization_id,
        resource_type="environment",
        resource_id=ctx.env.id,
        details={"project_id": str(ctx.project.id), "keys": sorted(values)},
    )
    await session.commit()
    return JSONResponse(RevealOut(values=values).model_dump(), headers=NO_STORE)


@router.patch("/variables", response_model=WriteOut)
async def batch_update(
    body: BatchIn,
    ctx: Ctx,
    request: Request,
    session: SessionDep,
    if_match: Annotated[str | None, Header()] = None,
):
    ctx.require(EnvAction.WRITE)
    try:
        result = await apply_changes(
            session,
            request,
            env_id=ctx.env.id,
            organization_id=ctx.membership.organization_id,
            project_id=ctx.project.id,
            actor_id=ctx.user_id,
            source=ctx.source,
            sets=[SetOp(u.key, u.value, u.visibility) for u in body.upserts],
            deletes=body.deletes,
            expected_revision=parse_if_match(if_match),
        )
    except VariableError as e:
        return error_response(e)
    return write_out(result)


@router.put("/variables/{key}", response_model=WriteOut)
async def set_variable(
    key: str, body: SingleSetIn, ctx: Ctx, request: Request, session: SessionDep
):
    ctx.require(EnvAction.WRITE)
    try:
        result = await apply_changes(
            session,
            request,
            env_id=ctx.env.id,
            organization_id=ctx.membership.organization_id,
            project_id=ctx.project.id,
            actor_id=ctx.user_id,
            source=ctx.source,
            sets=[SetOp(key, body.value, body.visibility)],
        )
    except VariableError as e:
        return error_response(e)
    return write_out(result)


@router.delete("/variables/{key}", response_model=WriteOut)
async def delete_variable(key: str, ctx: Ctx, request: Request, session: SessionDep):
    ctx.require(EnvAction.WRITE)
    try:
        result = await apply_changes(
            session,
            request,
            env_id=ctx.env.id,
            organization_id=ctx.membership.organization_id,
            project_id=ctx.project.id,
            actor_id=ctx.user_id,
            source=ctx.source,
            sets=[],
            deletes=[key],
        )
    except VariableError as e:
        return error_response(e)
    return write_out(result)


@router.post("/import", response_model=ImportOut)
async def import_dotenv(body: ImportIn, ctx: Ctx, request: Request, session: SessionDep):
    """Merge a .env document into the environment. Keys missing from the
    document are left alone; existing keys keep their visibility."""
    ctx.require(EnvAction.WRITE)
    parsed = dotenv.parse(body.content)
    if not parsed.ok:
        return JSONResponse(
            {
                "detail": "invalid_dotenv",
                "errors": [e.__dict__ for e in parsed.errors],
            },
            status_code=422,
        )
    sets = [SetOp(e.key, e.value, body.visibility.get(e.key)) for e in parsed.entries]
    # Existing keys keep their visibility: only pass it for new keys.
    existing = {v.key: v.visibility for v in await load_variables(session, ctx.env.id)}
    sets = [SetOp(s.key, s.value, None if s.key in existing else s.visibility) for s in sets]
    try:
        result = await apply_changes(
            session,
            request,
            env_id=ctx.env.id,
            organization_id=ctx.membership.organization_id,
            project_id=ctx.project.id,
            actor_id=ctx.user_id,
            source=ctx.source,
            sets=sets,
            dry_run=body.dry_run,
            message="import",
        )
    except VariableError as e:
        return error_response(e)

    changed = {c.key: c for c in result.changes}
    items = []
    for s in sets:
        if s.key not in existing:
            items.append(
                ImportItem(key=s.key, status="new", visibility=s.visibility or DEFAULT_VISIBILITY)
            )
        else:
            status = "changed" if s.key in changed else "unchanged"
            items.append(ImportItem(key=s.key, status=status, visibility=existing[s.key]))
    return ImportOut(revision=result.revision, dry_run=body.dry_run, items=items)


@router.get("/export")
async def export_variables(
    ctx: Ctx,
    request: Request,
    session: SessionDep,
    format: Annotated[Literal["dotenv", "json"], Query()] = "dotenv",
):
    """All values in plain text: the source for `envo pull` and `envo run`."""
    ctx.require(EnvAction.READ_SECRETS)
    variables = await load_variables(session, ctx.env.id)
    values = decrypt_all(ctx.env, variables)
    record(
        session,
        request,
        "variables.exported",
        actor_user_id=ctx.user_id,
        organization_id=ctx.membership.organization_id,
        resource_type="environment",
        resource_id=ctx.env.id,
        details={"project_id": str(ctx.project.id), "format": format, "count": len(values)},
    )
    await session.commit()
    headers = {**NO_STORE, "ETag": f'"{ctx.env.revision}"'}
    if format == "json":
        return JSONResponse(values, headers=headers)
    filename = f"{ctx.project.slug}.{ctx.env.slug}.env"
    headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return PlainTextResponse(
        dotenv.render(sorted(values.items())), headers=headers, media_type="text/plain"
    )
