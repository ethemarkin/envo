import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.deps import SessionDep
from app.core.errors import bad_request, forbidden, not_found
from app.modules.audit_logs.service import record
from app.modules.authorization.deps import ProjectAccess, ProjectActorDep
from app.modules.authorization.policy import EnvAction, can_env
from app.modules.environments.models import Environment
from app.modules.environments.router import get_project_environment
from app.modules.folders.paths import (
    ENV_FILE,
    ROOT,
    InvalidPath,
    file_key,
    file_name,
    join,
    label,
    normalize,
    normalize_name,
)
from app.modules.projects.models import Project
from app.modules.service_tokens.auth import TokenAccess
from app.modules.variables import dotenv
from app.modules.variables.models import Visibility
from app.modules.variables.schemas import (
    BatchIn,
    FileContentIn,
    FileOut,
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
    ensure_files,
    load_variables,
)
from app.modules.versions.models import ChangeAction, ChangeSource

router = APIRouter(
    prefix="/api/projects/{project_id}/environments/{env_id}",
    tags=["variables"],
)

NO_STORE = {"Cache-Control": "no-store"}


@dataclass
class EnvContext:
    access: ProjectAccess | TokenAccess
    env: Environment
    source: ChangeSource

    @property
    def project(self) -> Project:
        return self.access.project

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.access.user.id if isinstance(self.access, ProjectAccess) else None

    @property
    def token_id(self) -> uuid.UUID | None:
        return self.access.token.id if isinstance(self.access, TokenAccess) else None

    def allowed(self, action: EnvAction) -> bool:
        if isinstance(self.access, TokenAccess):
            # Tokens have no role: only their environments, writes if granted.
            if not self.access.allows_environment(self.env.id):
                return False
            return action != EnvAction.WRITE or self.access.token.can_write
        return can_env(self.access.role, action, self.env.protected)

    def require(self, action: EnvAction) -> None:
        if not self.allowed(action):
            raise forbidden()


async def env_context(
    env_id: uuid.UUID, request: Request, access: ProjectActorDep, session: SessionDep
) -> EnvContext:
    env = await get_project_environment(session, access.project.id, env_id)
    if isinstance(access, TokenAccess) and not access.allows_environment(env.id):
        # Environments outside the token's scope do not exist for it.
        raise not_found("environment_not_found")
    method = getattr(request.state, "auth_method", "web")
    return EnvContext(access, env, ChangeSource(method))


Ctx = Annotated[EnvContext, Depends(env_context)]


def folder_path(path: Annotated[str | None, Query(max_length=1024)] = None) -> str:
    """`?path=` selects the folder whose .env is addressed; default: the root."""
    try:
        return normalize(path)
    except InvalidPath:
        raise HTTPException(422, "invalid_path") from None


def optional_folder_path(
    path: Annotated[str | None, Query(max_length=1024)] = None,
) -> str | None:
    return None if path is None else folder_path(path)


FolderPath = Annotated[str, Depends(folder_path)]


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
async def list_variables(
    ctx: Ctx,
    session: SessionDep,
    path: Annotated[str | None, Depends(optional_folder_path)],
):
    """Variables of one folder (`?path=`), or of every folder when omitted."""
    ctx.require(EnvAction.LIST)
    stored = await load_variables(session, ctx.env.id, path)
    variables = [v for v in stored if file_name(v.key) is None]
    visible = [v for v in variables if v.visibility == Visibility.VISIBLE]
    plaintext = decrypt_all(ctx.env, visible)
    body = VariableListOut(
        # Config files with content in this environment; never their content.
        files=[
            FileOut(path=v.path, name=name, updated_at=v.updated_at)
            for v in stored
            if (name := file_name(v.key)) is not None
        ],
        revision=ctx.env.revision,
        protected=ctx.env.protected,
        can_read_secrets=ctx.allowed(EnvAction.READ_SECRETS),
        can_write=ctx.allowed(EnvAction.WRITE),
        variables=[
            VariableOut(
                path=v.path,
                key=v.key,
                visibility=v.visibility,
                value=plaintext.get((v.path, v.key)),
                updated_at=v.updated_at,
            )
            for v in variables
        ],
    )
    return JSONResponse(
        body.model_dump(mode="json"), headers={"ETag": f'"{ctx.env.revision}"', **NO_STORE}
    )


@router.post("/variables/reveal", response_model=RevealOut)
async def reveal_variables(
    body: RevealIn, ctx: Ctx, request: Request, session: SessionDep, path: FolderPath
):
    ctx.require(EnvAction.READ_SECRETS)
    variables = await load_variables(session, ctx.env.id, path, "variables")
    if body.keys is not None:
        wanted = set(body.keys)
        variables = [v for v in variables if v.key in wanted]
    else:
        variables = [v for v in variables if v.visibility == Visibility.SECRET]
    values = {key: value for (_, key), value in decrypt_all(ctx.env, variables).items()}
    record(
        session,
        request,
        "variables.revealed",
        actor_user_id=ctx.user_id,
        actor_token_id=ctx.token_id,
        project_id=ctx.project.id,
        group_id=ctx.project.group_id,
        resource_type="environment",
        resource_id=ctx.env.id,
        details={
            "environment": ctx.env.slug,
            "keys": sorted(label(path, k) for k in values),
        },
    )
    await session.commit()
    return JSONResponse(RevealOut(values=values).model_dump(), headers=NO_STORE)


@router.patch("/variables", response_model=WriteOut)
async def batch_update(
    body: BatchIn,
    ctx: Ctx,
    request: Request,
    session: SessionDep,
    path: FolderPath,
    if_match: Annotated[str | None, Header()] = None,
):
    ctx.require(EnvAction.WRITE)
    try:
        result = await apply_changes(
            session,
            request,
            env_id=ctx.env.id,
            group_id=ctx.project.group_id,
            project_id=ctx.project.id,
            actor_id=ctx.user_id,
            actor_token_id=ctx.token_id,
            source=ctx.source,
            sets=[SetOp(u.key, u.value, u.visibility, path) for u in body.upserts],
            deletes=[(path, k) for k in body.deletes],
            expected_revision=parse_if_match(if_match),
        )
    except VariableError as e:
        return error_response(e)
    return write_out(result)


@router.put("/variables/{key}", response_model=WriteOut)
async def set_variable(
    key: str, body: SingleSetIn, ctx: Ctx, request: Request, session: SessionDep, path: FolderPath
):
    ctx.require(EnvAction.WRITE)
    try:
        result = await apply_changes(
            session,
            request,
            env_id=ctx.env.id,
            group_id=ctx.project.group_id,
            project_id=ctx.project.id,
            actor_id=ctx.user_id,
            actor_token_id=ctx.token_id,
            source=ctx.source,
            sets=[SetOp(key, body.value, body.visibility, path)],
        )
    except VariableError as e:
        return error_response(e)
    return write_out(result)


@router.delete("/variables/{key}", response_model=WriteOut)
async def delete_variable(
    key: str, ctx: Ctx, request: Request, session: SessionDep, path: FolderPath
):
    ctx.require(EnvAction.WRITE)
    try:
        result = await apply_changes(
            session,
            request,
            env_id=ctx.env.id,
            group_id=ctx.project.group_id,
            project_id=ctx.project.id,
            actor_id=ctx.user_id,
            actor_token_id=ctx.token_id,
            source=ctx.source,
            sets=[],
            deletes=[(path, key)],
        )
    except VariableError as e:
        return error_response(e)
    return write_out(result)


@router.post("/import", response_model=ImportOut)
async def import_dotenv(
    body: ImportIn,
    ctx: Ctx,
    request: Request,
    session: SessionDep,
    path: FolderPath,
    if_match: Annotated[str | None, Header()] = None,
):
    """Write a .env document into one folder of the environment. Existing
    keys keep their visibility. By default keys missing from the document are
    left alone (merge); with `replace` they are deleted, so the folder's .env
    becomes exactly the document (the web .env editor)."""
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
    # Existing keys keep their visibility: only pass it for new keys.
    existing = {
        v.key: v.visibility for v in await load_variables(session, ctx.env.id, path, "variables")
    }
    sets = [
        SetOp(e.key, e.value, None if e.key in existing else body.visibility.get(e.key), path)
        for e in parsed.entries
    ]
    in_document = {s.key for s in sets}
    removed = sorted(k for k in existing if k not in in_document) if body.replace else []
    try:
        result = await apply_changes(
            session,
            request,
            env_id=ctx.env.id,
            group_id=ctx.project.group_id,
            project_id=ctx.project.id,
            actor_id=ctx.user_id,
            actor_token_id=ctx.token_id,
            source=ctx.source,
            sets=sets,
            deletes=[(path, k) for k in removed],
            expected_revision=parse_if_match(if_match),
            dry_run=body.dry_run,
            message="edit .env" if body.replace else "import",
        )
    except VariableError as e:
        return error_response(e)

    changed = {c.key for c in result.changes}
    items = []
    for s in sets:
        if s.key not in existing:
            items.append(
                ImportItem(key=s.key, status="new", visibility=s.visibility or DEFAULT_VISIBILITY)
            )
        else:
            status = "changed" if s.key in changed else "unchanged"
            items.append(ImportItem(key=s.key, status=status, visibility=existing[s.key]))
    items += [ImportItem(key=k, status="deleted", visibility=existing[k]) for k in removed]
    return ImportOut(revision=result.revision, dry_run=body.dry_run, items=items)


@router.get("/export")
async def export_variables(
    ctx: Ctx,
    request: Request,
    session: SessionDep,
    path: FolderPath,
    format: Annotated[Literal["dotenv", "json"], Query()] = "dotenv",
):
    """One folder's values in plain text (default: the root folder): the
    source for `envo pull` and `envo run`, and for the web .env editor."""
    ctx.require(EnvAction.READ_SECRETS)
    variables = await load_variables(session, ctx.env.id, path, "variables")
    values = {key: value for (_, key), value in decrypt_all(ctx.env, variables).items()}
    record(
        session,
        request,
        "variables.exported",
        actor_user_id=ctx.user_id,
        actor_token_id=ctx.token_id,
        project_id=ctx.project.id,
        group_id=ctx.project.group_id,
        resource_type="environment",
        resource_id=ctx.env.id,
        details={
            "environment": ctx.env.slug,
            "path": path,
            "format": format,
            "count": len(values),
        },
    )
    await session.commit()
    headers = {**NO_STORE, "ETag": f'"{ctx.env.revision}"'}
    if format == "json":
        return JSONResponse(values, headers=headers)
    folder = "." + path.replace("/", ".") if path != ROOT else ""
    filename = f"{ctx.project.slug}{folder}.{ctx.env.slug}.env"
    headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return PlainTextResponse(
        dotenv.render(sorted(values.items())), headers=headers, media_type="text/plain"
    )


# --- Config files ----------------------------------------------------------
#
# A config file (application.properties, config.json, ...) is placed in a
# folder by the project (see folders.router) and has its own content in every
# environment. The content is opaque text, stored encrypted like a secret
# variable; an empty file has no stored content.


def config_file_name(name: str) -> str:
    try:
        name = normalize_name(name)
    except InvalidPath:
        raise HTTPException(422, "invalid_file_name") from None
    if name == ENV_FILE:
        # The .env is a set of variables: use /export and /import.
        raise HTTPException(422, "invalid_file_name")
    return name


ConfigFileName = Annotated[str, Depends(config_file_name)]


@router.get("/files/{name}")
async def read_file(
    name: ConfigFileName, ctx: Ctx, request: Request, session: SessionDep, path: FolderPath
):
    """A config file's content in this environment (empty when it has none),
    with the environment revision as ETag."""
    ctx.require(EnvAction.READ_SECRETS)
    stored = [
        v
        for v in await load_variables(session, ctx.env.id, path, "files")
        if v.key == file_key(name)
    ]
    content = next(iter(decrypt_all(ctx.env, stored).values()), "")
    record(
        session,
        request,
        "variables.file_read",
        actor_user_id=ctx.user_id,
        actor_token_id=ctx.token_id,
        project_id=ctx.project.id,
        group_id=ctx.project.group_id,
        resource_type="environment",
        resource_id=ctx.env.id,
        details={"environment": ctx.env.slug, "file": join(path, name)},
    )
    await session.commit()
    return PlainTextResponse(
        content,
        media_type="text/plain",
        headers={
            **NO_STORE,
            "ETag": f'"{ctx.env.revision}"',
            "Content-Disposition": f'attachment; filename="{name}"',
        },
    )


@router.put("/files/{name}", response_model=WriteOut)
async def write_file(
    name: ConfigFileName,
    body: FileContentIn,
    ctx: Ctx,
    request: Request,
    session: SessionDep,
    path: FolderPath,
    if_match: Annotated[str | None, Header()] = None,
):
    """Replace a config file's content in this environment, as one revision.
    Writing to a file the project does not have yet places it (like a .env
    push). Empty content clears the file."""
    ctx.require(EnvAction.WRITE)
    key = file_key(name)
    exists = any(v.key == key for v in await load_variables(session, ctx.env.id, path, "files"))
    sets, deletes = [], []
    if body.content:
        sets = [SetOp(key, body.content, Visibility.SECRET, path)]
    elif exists:
        deletes = [(path, key)]
    try:
        result = await apply_changes(
            session,
            request,
            env_id=ctx.env.id,
            group_id=ctx.project.group_id,
            project_id=ctx.project.id,
            actor_id=ctx.user_id,
            actor_token_id=ctx.token_id,
            source=ctx.source,
            sets=sets,
            deletes=deletes,
            expected_revision=parse_if_match(if_match),
            message=f"edit {join(path, name)}",
        )
    except VariableError as e:
        return error_response(e)
    if not body.content and not exists:
        # Nothing stored either way; still make sure the file is placed.
        await ensure_files(session, ctx.project.id, {(path, name)})
        await session.commit()
    return write_out(result)
