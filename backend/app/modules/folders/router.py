"""The project's folder tree and the places that hold a .env, shared by all
environments.

Folders are structure; a .env exists only where the project places one (the
root or a folder), and then in every environment (variables carry its path).
Moving or deleting a folder, or removing a .env, rewrites the affected
variables
in every environment, each as a new revision of that environment, all in one
transaction: history shows what moved, and rolling an environment back to an
older revision restores the folders it used.
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
from app.modules.folders.models import ProjectEnvFile, ProjectFolder
from app.modules.folders.paths import ROOT, InvalidPath, label, moved, normalize, within
from app.modules.service_tokens.auth import TokenAccess
from app.modules.variables.models import Variable
from app.modules.variables.service import (
    SetOp,
    VariableError,
    apply_changes,
    decrypt_all,
    ensure_env_files,
    ensure_folders,
    load_variables,
    lock_environment,
)
from app.modules.versions.models import ChangeSource

router = APIRouter(prefix="/api/projects/{project_id}/folders", tags=["folders"])


class FolderListOut(BaseModel):
    # Always starts with "" (the project root); sorted.
    folders: list[str]
    # Where a .env lives ("" is the root); sorted.
    env_files: list[str]
    can_manage: bool


class FolderIn(BaseModel):
    path: str = Field(max_length=1024)
    # Also place a .env in the new folder.
    env: bool = False


class EnvFileIn(BaseModel):
    # "" places the .env at the project root.
    path: str = Field(max_length=1024)


class FolderMoveIn(BaseModel):
    path: str = Field(max_length=1024)
    new_path: str = Field(max_length=1024)


class FolderChangeOut(BaseModel):
    folders: list[str]
    env_files: list[str]
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


async def folder_paths(session: AsyncSession, project_id) -> list[str]:
    rows = await session.scalars(
        select(ProjectFolder.path).where(ProjectFolder.project_id == project_id)
    )
    return [ROOT, *sorted(rows)]


async def env_file_paths(session: AsyncSession, project_id) -> list[str]:
    rows = await session.scalars(
        select(ProjectEnvFile.path).where(ProjectEnvFile.project_id == project_id)
    )
    return sorted(rows)


async def change_out(session: AsyncSession, project_id, environments: list[str]):
    return FolderChangeOut(
        folders=await folder_paths(session, project_id),
        env_files=await env_file_paths(session, project_id),
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
    return FolderListOut(
        folders=await folder_paths(session, access.project.id),
        env_files=await env_file_paths(session, access.project.id),
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
    exact: bool = False,
) -> list[str]:
    """Move (target set) or delete (target None) the variables below `folder`
    in every environment; with `exact`, only those of `folder`'s own .env.
    Returns the slugs of the changed environments. Does not commit."""

    def selected(path: str) -> bool:
        return path == folder if exact else within(path, folder)

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
            .where(Variable.path == folder if exact else in_subtree(Variable.path, folder))
            .distinct()
        )
    )
    affected_envs = [e for e in envs if e.id in affected]
    if any(not can_env(access.role, EnvAction.WRITE, e.protected) for e in affected_envs):
        raise forbidden()

    method = getattr(request.state, "auth_method", "web")
    for env in affected_envs:
        variables = [v for v in await load_variables(session, env.id) if selected(v.path)]
        values = decrypt_all(env, variables)
        sets = []
        if target is not None:
            sets = [
                SetOp(v.key, values[(v.path, v.key)], v.visibility, moved(v.path, folder, target))
                for v in variables
            ]
        if target is not None:
            message = f"move {folder} -> {target}"
        elif exact:
            message = f"remove {label(folder, '.env')}"
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
    """Rename or move a folder with its subfolders. Its .env files move along
    in every environment."""
    access.ensure(Action.FOLDER_MANAGE)
    folder, target = parse(body.path), parse(body.new_path)
    existing = await folder_paths(session, access.project.id)
    if folder not in existing:
        raise not_found("folder_not_found")
    if within(target, folder):
        raise HTTPException(422, "folder_into_itself")
    if any(within(p, target) for p in existing):
        raise conflict("folder_exists")

    # Rename the folder rows first: writing variables into the new paths
    # would otherwise create them a second time.
    rows = await session.scalars(
        select(ProjectFolder).where(
            ProjectFolder.project_id == access.project.id, in_subtree(ProjectFolder.path, folder)
        )
    )
    for row in rows:
        row.path = moved(row.path, folder, target)
    env_rows = await session.scalars(
        select(ProjectEnvFile).where(
            ProjectEnvFile.project_id == access.project.id,
            in_subtree(ProjectEnvFile.path, folder),
        )
    )
    for env_row in env_rows:
        env_row.path = moved(env_row.path, folder, target)
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
    """Delete a folder, its subfolders and their .env files in every
    environment. Each environment's history keeps the deleted values."""
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
    env_rows = await session.scalars(
        select(ProjectEnvFile).where(
            ProjectEnvFile.project_id == access.project.id,
            in_subtree(ProjectEnvFile.path, folder),
        )
    )
    for env_row in env_rows:
        await session.delete(env_row)
    _audit(session, request, access, "folder.deleted", path=folder)
    await session.commit()
    return await change_out(session, access.project.id, changed)


@router.post("/env", response_model=FolderChangeOut, status_code=status.HTTP_201_CREATED)
async def add_env_file(
    body: EnvFileIn, access: ProjectAccessDep, request: Request, session: SessionDep
):
    """Place a .env at the root or in a folder (creating missing folders). It
    starts empty in every environment."""
    access.ensure(Action.FOLDER_MANAGE)
    path = parse(body.path, root_ok=True)
    if path in await env_file_paths(session, access.project.id):
        raise conflict("env_file_exists")
    await ensure_env_files(session, access.project.id, {path})
    _audit(session, request, access, "folder.env_added", path=path)
    await session.commit()
    return await change_out(session, access.project.id, [])


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
    folder = parse(path, root_ok=True)
    row = await session.scalar(
        select(ProjectEnvFile).where(
            ProjectEnvFile.project_id == access.project.id, ProjectEnvFile.path == folder
        )
    )
    if row is None:
        raise not_found("env_file_not_found")
    try:
        changed = await _rewrite_subtree(session, request, access, folder, None, exact=True)
    except VariableError as e:
        await session.rollback()
        raise HTTPException(e.status, e.code) from None
    await session.delete(row)
    _audit(session, request, access, "folder.env_removed", path=folder)
    await session.commit()
    return await change_out(session, access.project.id, changed)
