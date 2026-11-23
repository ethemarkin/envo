"""The project's folder tree and the files placed in it, shared by all
environments.

Folders are structure; a .env or a config file (application.properties,
config.json, ...) exists only where the project places one (the root or a
folder), and then in every environment, each with its own content.
Moving or deleting a folder, or removing a file, rewrites the affected
variables and file contents in every environment, each as a new revision of
that environment, all in one transaction: history shows what moved, and
rolling an environment back to an older revision restores the folders it used.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import SessionDep
from app.core.errors import conflict, forbidden, not_found
from app.modules.audit_logs.service import record
from app.modules.authorization.deps import ProjectAccess, ProjectAccessDep, ProjectActorDep
from app.modules.authorization.policy import Action, EnvAction, can, can_env
from app.modules.environments.models import Environment
from app.modules.folders.models import ProjectFile, ProjectFolder
from app.modules.folders.paths import (
    ENV_FILE,
    ROOT,
    InvalidPath,
    ancestors,
    file_key,
    join,
    moved,
    normalize,
    normalize_name,
    owner,
    within,
)
from app.modules.service_tokens.auth import TokenAccess
from app.modules.variables.models import Variable
from app.modules.variables.service import (
    SetOp,
    VariableError,
    apply_changes,
    decrypt_all,
    ensure_env_files,
    ensure_files,
    ensure_folders,
    is_file_key,
    load_variables,
    lock_environment,
)
from app.modules.versions.models import ChangeSource

router = APIRouter(prefix="/api/projects/{project_id}/folders", tags=["folders"])


class FileOut(BaseModel):
    # Folder holding the file; "" is the project root.
    path: str
    # ".env" or a config file name such as "application.properties".
    name: str


class FolderListOut(BaseModel):
    # Always starts with "" (the project root); sorted.
    folders: list[str]
    # Where a .env lives ("" is the root); sorted.
    env_files: list[str]
    # Every placed file, .env files included; sorted by path, then name.
    files: list[FileOut]
    can_manage: bool


class FolderIn(BaseModel):
    path: str = Field(max_length=1024)
    # Also place a .env in the new folder.
    env: bool = False


class EnvFileIn(BaseModel):
    # "" places the .env at the project root.
    path: str = Field(max_length=1024)


class FileIn(BaseModel):
    # "" places the file at the project root.
    path: str = Field(max_length=1024)
    name: str = Field(max_length=255)


class FolderMoveIn(BaseModel):
    path: str = Field(max_length=1024)
    new_path: str = Field(max_length=1024)


class FolderChangeOut(BaseModel):
    folders: list[str]
    env_files: list[str]
    files: list[FileOut]
    # Environments that got a new revision, by slug.
    environments: list[str]


def parse(raw: str, root_ok: bool = False) -> str:
    try:
        path = normalize(raw)
    except InvalidPath:
        raise HTTPException(422, "invalid_path") from None
    if path == ROOT and not root_ok:
        raise HTTPException(422, "invalid_path")
    return path


def parse_name(raw: str) -> str:
    try:
        return normalize_name(raw)
    except InvalidPath:
        raise HTTPException(422, "invalid_file_name") from None


async def folder_paths(session: AsyncSession, project_id) -> list[str]:
    rows = await session.scalars(
        select(ProjectFolder.path).where(ProjectFolder.project_id == project_id)
    )
    return [ROOT, *sorted(rows)]


async def project_files(session: AsyncSession, project_id) -> list[FileOut]:
    rows = await session.execute(
        select(ProjectFile.path, ProjectFile.name)
        .where(ProjectFile.project_id == project_id)
        .order_by(ProjectFile.path, ProjectFile.name)
    )
    return [FileOut(path=path, name=name) for path, name in rows]


async def file_clash(session: AsyncSession, project_id, path: str) -> bool:
    """Whether `path` or a folder above it is already a placed file (a folder
    and a file cannot share a name in a checkout)."""
    taken = {join(f.path, f.name) for f in await project_files(session, project_id)}
    return any(p in taken for p in [*ancestors(path), path])


async def change_out(session: AsyncSession, project_id, environments: list[str]):
    files = await project_files(session, project_id)
    return FolderChangeOut(
        folders=await folder_paths(session, project_id),
        env_files=[f.path for f in files if f.name == ENV_FILE],
        files=files,
        environments=environments,
    )


def in_subtree(column, folder: str):
    return or_(column == folder, column.startswith(folder + "/", autoescape=True))


@router.get("", response_model=FolderListOut)
async def list_folders(access: ProjectActorDep, session: SessionDep):
    if isinstance(access, TokenAccess):
        manage = False
    else:
        access.ensure(Action.READ)
        manage = can(access.role, Action.FOLDER_MANAGE)
    files = await project_files(session, access.project.id)
    return FolderListOut(
        folders=await folder_paths(session, access.project.id),
        env_files=[f.path for f in files if f.name == ENV_FILE],
        files=files,
        can_manage=manage,
    )


def _audit(session, request, access: ProjectAccess, action: str, **details) -> None:
    record(
        session,
        request,
        action,
        actor_user_id=access.user.id,
        project_id=access.project.id,
        group_id=access.project.group_id,
        resource_type="project",
        resource_id=access.project.id,
        details=details,
    )


@router.post("", response_model=FolderChangeOut, status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderIn, access: ProjectAccessDep, request: Request, session: SessionDep
):
    """Add a folder (and any missing parents). With `env` it also gets an
    empty .env in every environment."""
    access.ensure(Action.FOLDER_MANAGE)
    path = parse(body.path)
    existing = await folder_paths(session, access.project.id)
    if path in existing:
        raise conflict("folder_exists")
    if await file_clash(session, access.project.id, path):
        raise conflict("file_exists")
    await ensure_folders(session, access.project.id, {path})
    if body.env:
        await ensure_env_files(session, access.project.id, {path})
    _audit(session, request, access, "folder.created", path=path, env=body.env)
    await session.commit()
    return await change_out(session, access.project.id, [])


async def _rewrite_subtree(
    session: AsyncSession,
    request: Request,
    access: ProjectAccess,
    folder: str,
    target: str | None,
    file: str | None = None,
) -> list[str]:
    """Move (target set) or delete (target None) the variables and file
    contents below `folder` in every environment; with `file`, only that one
    file of `folder` (".env" or a config file name).
    Returns the slugs of the changed environments. Does not commit."""

    def selected(v: Variable) -> bool:
        if file is None:
            return within(v.path, folder)
        return v.path == folder and owner(v.key) == file

    if file is None:
        where = in_subtree(Variable.path, folder)
    elif file == ENV_FILE:
        where = (Variable.path == folder) & ~is_file_key()
    else:
        where = (Variable.path == folder) & (Variable.key == file_key(file))

    envs = list(
        await session.scalars(
            select(Environment)
            .where(Environment.project_id == access.project.id)
            .order_by(Environment.id)
        )
    )
    # Lock first (in a fixed order), then read: values copied to the new
    # folder cannot be overwritten concurrently in between.
    for env in envs:
        await lock_environment(session, env.id)
    affected = set(
        await session.scalars(
            select(Variable.environment_id)
            .where(Variable.environment_id.in_([e.id for e in envs]))
            .where(where)
            .distinct()
        )
    )
    affected_envs = [e for e in envs if e.id in affected]
    if any(not can_env(access.role, EnvAction.WRITE, e.protected) for e in affected_envs):
        raise forbidden()

    method = getattr(request.state, "auth_method", "web")
    for env in affected_envs:
        variables = [v for v in await load_variables(session, env.id) if selected(v)]
        values = decrypt_all(env, variables)
        sets = []
        if target is not None:
            sets = [
                SetOp(v.key, values[(v.path, v.key)], v.visibility, moved(v.path, folder, target))
                for v in variables
            ]
        if target is not None:
            message = f"move {folder} -> {target}"
        elif file is not None:
            message = f"remove {join(folder, file)}"
        else:
            message = f"delete {folder}"
        await apply_changes(
            session,
            request,
            env_id=env.id,
            group_id=access.project.group_id,
            project_id=access.project.id,
            actor_id=access.user.id,
            source=ChangeSource(method),
            sets=sets,
            deletes=[(v.path, v.key) for v in variables],
            message=message,
            commit=False,
        )
    return [e.slug for e in affected_envs]


@router.patch("", response_model=FolderChangeOut)
async def move_folder(
    body: FolderMoveIn, access: ProjectAccessDep, request: Request, session: SessionDep
):
    """Rename or move a folder with its subfolders. Its files move along in
    every environment."""
    access.ensure(Action.FOLDER_MANAGE)
    folder, target = parse(body.path), parse(body.new_path)
    existing = await folder_paths(session, access.project.id)
    if folder not in existing:
        raise not_found("folder_not_found")
    if within(target, folder):
        raise HTTPException(422, "folder_into_itself")
    if any(within(p, target) for p in existing):
        raise conflict("folder_exists")
    if await file_clash(session, access.project.id, target):
        raise conflict("file_exists")

    # Rename the folder and file rows first: writing variables into the new
    # paths would otherwise create them a second time.
    rows = await session.scalars(
        select(ProjectFolder).where(
            ProjectFolder.project_id == access.project.id, in_subtree(ProjectFolder.path, folder)
        )
    )
    for row in rows:
        row.path = moved(row.path, folder, target)
    file_rows = await session.scalars(
        select(ProjectFile).where(
            ProjectFile.project_id == access.project.id,
            in_subtree(ProjectFile.path, folder),
        )
    )
    for file_row in file_rows:
        file_row.path = moved(file_row.path, folder, target)
    await session.flush()
    await ensure_folders(session, access.project.id, {target})
    try:
        changed = await _rewrite_subtree(session, request, access, folder, target)
    except VariableError as e:
        await session.rollback()
        raise HTTPException(e.status, e.code) from None
    _audit(session, request, access, "folder.moved", path=folder, new_path=target)
    await session.commit()
    return await change_out(session, access.project.id, changed)


@router.delete("", response_model=FolderChangeOut)
async def delete_folder(
    access: ProjectAccessDep,
    request: Request,
    session: SessionDep,
    path: Annotated[str, Query(max_length=1024)] = "",
):
    """Delete a folder, its subfolders and their files in every environment.
    Each environment's history keeps the deleted values."""
    access.ensure(Action.FOLDER_MANAGE)
    folder = parse(path)
    if folder not in await folder_paths(session, access.project.id):
        raise not_found("folder_not_found")
    try:
        changed = await _rewrite_subtree(session, request, access, folder, None)
    except VariableError as e:
        await session.rollback()
        raise HTTPException(e.status, e.code) from None
    rows = await session.scalars(
        select(ProjectFolder).where(
            ProjectFolder.project_id == access.project.id, in_subtree(ProjectFolder.path, folder)
        )
    )
    for row in rows:
        await session.delete(row)
    file_rows = await session.scalars(
        select(ProjectFile).where(
            ProjectFile.project_id == access.project.id,
            in_subtree(ProjectFile.path, folder),
        )
    )
    for file_row in file_rows:
        await session.delete(file_row)
    _audit(session, request, access, "folder.deleted", path=folder)
    await session.commit()
    return await change_out(session, access.project.id, changed)


async def _add_file(
    session: AsyncSession, request: Request, access: ProjectAccess, path: str, name: str
) -> FolderChangeOut:
    files = await project_files(session, access.project.id)
    if any(f.path == path and f.name == name for f in files):
        raise conflict("env_file_exists" if name == ENV_FILE else "file_exists")
    if join(path, name) in await folder_paths(session, access.project.id):
        raise conflict("folder_exists")
    if path and await file_clash(session, access.project.id, path):
        raise conflict("file_exists")
    await ensure_files(session, access.project.id, {(path, name)})
    if name == ENV_FILE:
        _audit(session, request, access, "folder.env_added", path=path)
    else:
        _audit(session, request, access, "folder.file_added", path=path, name=name)
    await session.commit()
    return await change_out(session, access.project.id, [])


async def _remove_file(
    session: AsyncSession, request: Request, access: ProjectAccess, path: str, name: str
) -> FolderChangeOut:
    row = await session.scalar(
        select(ProjectFile).where(
            ProjectFile.project_id == access.project.id,
            ProjectFile.path == path,
            ProjectFile.name == name,
        )
    )
    if row is None:
        raise not_found("env_file_not_found" if name == ENV_FILE else "file_not_found")
    try:
        changed = await _rewrite_subtree(session, request, access, path, None, file=name)
    except VariableError as e:
        await session.rollback()
        raise HTTPException(e.status, e.code) from None
    await session.delete(row)
    if name == ENV_FILE:
        _audit(session, request, access, "folder.env_removed", path=path)
    else:
        _audit(session, request, access, "folder.file_removed", path=path, name=name)
    await session.commit()
    return await change_out(session, access.project.id, changed)


@router.post("/env", response_model=FolderChangeOut, status_code=status.HTTP_201_CREATED)
async def add_env_file(
    body: EnvFileIn, access: ProjectAccessDep, request: Request, session: SessionDep
):
    """Place a .env at the root or in a folder (creating missing folders). It
    starts empty in every environment."""
    access.ensure(Action.FOLDER_MANAGE)
    return await _add_file(session, request, access, parse(body.path, root_ok=True), ENV_FILE)


@router.delete("/env", response_model=FolderChangeOut)
async def remove_env_file(
    access: ProjectAccessDep,
    request: Request,
    session: SessionDep,
    path: Annotated[str, Query(max_length=1024)] = "",
):
    """Remove the .env of the root or a folder, with its values, in every
    environment. The folder itself stays; history keeps the values."""
    access.ensure(Action.FOLDER_MANAGE)
    return await _remove_file(session, request, access, parse(path, root_ok=True), ENV_FILE)


@router.post("/files", response_model=FolderChangeOut, status_code=status.HTTP_201_CREATED)
async def add_file(body: FileIn, access: ProjectAccessDep, request: Request, session: SessionDep):
    """Place a file (".env" or a config file such as application.properties)
    at the root or in a folder, creating missing folders. It starts empty in
    every environment."""
    access.ensure(Action.FOLDER_MANAGE)
    path, name = parse(body.path, root_ok=True), parse_name(body.name)
    return await _add_file(session, request, access, path, name)


@router.delete("/files", response_model=FolderChangeOut)
async def remove_file(
    access: ProjectAccessDep,
    request: Request,
    session: SessionDep,
    name: Annotated[str, Query(max_length=255)],
    path: Annotated[str, Query(max_length=1024)] = "",
):
    """Remove a file of the root or a folder, with its content, in every
    environment. The folder itself stays; history keeps the content."""
    access.ensure(Action.FOLDER_MANAGE)
    path, name = parse(path, root_ok=True), parse_name(name)
    return await _remove_file(session, request, access, path, name)
