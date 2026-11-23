"""The project's folder tree, shared by all environments.

Each folder has its own .env in every environment (variables carry the
folder's path). Moving or deleting a folder rewrites the variables below it
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
from app.modules.folders.models import ProjectFolder
from app.modules.folders.paths import ROOT, InvalidPath, moved, normalize, within
from app.modules.service_tokens.auth import TokenAccess
from app.modules.variables.models import Variable
from app.modules.variables.service import (
    SetOp,
    VariableError,
    apply_changes,
    decrypt_all,
    ensure_folders,
    load_variables,
    lock_environment,
)
from app.modules.versions.models import ChangeSource

router = APIRouter(prefix="/api/projects/{project_id}/folders", tags=["folders"])


class FolderListOut(BaseModel):
    # Always starts with "" (the project root); sorted.
    folders: list[str]
    can_manage: bool


class FolderIn(BaseModel):
    path: str = Field(max_length=1024)


class FolderMoveIn(BaseModel):
    path: str = Field(max_length=1024)
    new_path: str = Field(max_length=1024)


class FolderChangeOut(BaseModel):
    folders: list[str]
    # Environments that got a new revision, by slug.
    environments: list[str]


def parse(raw: str) -> str:
    try:
        path = normalize(raw)
    except InvalidPath:
        raise HTTPException(422, "invalid_path") from None
    if path == ROOT:
        raise HTTPException(422, "invalid_path")
    return path


async def folder_paths(session: AsyncSession, project_id) -> list[str]:
    rows = await session.scalars(
        select(ProjectFolder.path).where(ProjectFolder.project_id == project_id)
    )
    return [ROOT, *sorted(rows)]


def in_subtree(column, folder: str):
    return or_(column == folder, column.startswith(folder + "/", autoescape=True))


@router.get("", response_model=FolderListOut)
async def list_folders(access: ProjectActorDep, session: SessionDep):
    if isinstance(access, TokenAccess):
        manage = False
    else:
        access.ensure(Action.READ)
        manage = can(access.role, Action.FOLDER_MANAGE)
    return FolderListOut(folders=await folder_paths(session, access.project.id), can_manage=manage)


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
    """Add a folder (and any missing parents). It starts with an empty .env
    in every environment."""
    access.ensure(Action.FOLDER_MANAGE)
    path = parse(body.path)
    existing = await folder_paths(session, access.project.id)
    if path in existing:
        raise conflict("folder_exists")
    await ensure_folders(session, access.project.id, {path})
    _audit(session, request, access, "folder.created", path=path)
    await session.commit()
    return FolderChangeOut(folders=await folder_paths(session, access.project.id), environments=[])


async def _rewrite_subtree(
    session: AsyncSession,
    request: Request,
    access: ProjectAccess,
    folder: str,
    target: str | None,
) -> list[str]:
    """Move (target set) or delete (target None) the variables below `folder`
    in every environment. Returns the slugs of the changed environments.
    Does not commit."""
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
            .where(in_subtree(Variable.path, folder))
            .distinct()
        )
    )
    affected_envs = [e for e in envs if e.id in affected]
    if any(not can_env(access.role, EnvAction.WRITE, e.protected) for e in affected_envs):
        raise forbidden()

    method = getattr(request.state, "auth_method", "web")
    for env in affected_envs:
        variables = [v for v in await load_variables(session, env.id) if within(v.path, folder)]
        values = decrypt_all(env, variables)
        sets = []
        if target is not None:
            sets = [
                SetOp(v.key, values[(v.path, v.key)], v.visibility, moved(v.path, folder, target))
                for v in variables
            ]
        message = f"move {folder} -> {target}" if target is not None else f"delete {folder}"
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
    await session.flush()
    await ensure_folders(session, access.project.id, {target})
    try:
        changed = await _rewrite_subtree(session, request, access, folder, target)
    except VariableError as e:
        await session.rollback()
        raise HTTPException(e.status, e.code) from None
    _audit(session, request, access, "folder.moved", path=folder, new_path=target)
    await session.commit()
    return FolderChangeOut(
        folders=await folder_paths(session, access.project.id), environments=changed
    )


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
    _audit(session, request, access, "folder.deleted", path=folder)
    await session.commit()
    return FolderChangeOut(
        folders=await folder_paths(session, access.project.id), environments=changed
    )
