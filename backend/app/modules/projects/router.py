import uuid

from fastapi import APIRouter, Request, status

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import conflict, forbidden
from app.modules.audit_logs.service import record
from app.modules.authorization import members
from app.modules.authorization.access import can_create_root
from app.modules.authorization.deps import (
    ProjectAccess,
    ProjectAccessDep,
    load_group_access,
    load_project_access,
)
from app.modules.authorization.policy import Action, Role
from app.modules.environments.models import DEFAULT_ENVIRONMENTS, Environment
from app.modules.folders.models import ProjectEnvFile
from app.modules.folders.paths import ROOT
from app.modules.groups.namespace import choose_slug, slug_taken
from app.modules.groups.schemas import BreadcrumbOut
from app.modules.projects.models import Project, ProjectMember
from app.modules.projects.schemas import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])


def project_out(access: ProjectAccess) -> ProjectOut:
    p = access.project
    return ProjectOut(
        id=p.id,
        group_id=p.group_id,
        name=p.name,
        slug=p.slug,
        path=access.path,
        description=p.description,
        role=access.role,
        ancestors=[
            BreadcrumbOut(id=g.id, name=g.name, slug=g.slug) for g in reversed(access.chain)
        ],
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate, user: CurrentUser, request: Request, session: SessionDep
):
    if body.group_id is None:
        if not await can_create_root(session, user):
            raise forbidden("root_creation_disabled")
    else:
        group = await load_group_access(session, user, body.group_id)
        group.ensure(Action.CREATE_CHILD)

    slug = await choose_slug(session, body.group_id, body.slug, body.name, "project")
    project = Project(
        group_id=body.group_id, name=body.name, slug=slug, description=body.description
    )
    session.add(project)
    await session.flush()
    if body.group_id is None:
        # Top-level projects start with their creator as owner.
        session.add(ProjectMember(project_id=project.id, user_id=user.id, role=Role.OWNER))
    # New projects start with a .env at the root; it can be removed.
    session.add(ProjectEnvFile(project_id=project.id, path=ROOT))
    for name, env_slug, protected in DEFAULT_ENVIRONMENTS:
        session.add(
            Environment(project_id=project.id, name=name, slug=env_slug, protected=protected)
        )
    record(
        session,
        request,
        "project.created",
        actor_user_id=user.id,
        project_id=project.id,
        group_id=body.group_id,
        resource_type="project",
        resource_id=project.id,
        details={"slug": slug},
    )
    await session.commit()
    return project_out(await load_project_access(session, user, project.id))


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(access: ProjectAccessDep):
    access.ensure(Action.READ)
    return project_out(access)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    body: ProjectUpdate, access: ProjectAccessDep, request: Request, session: SessionDep
):
    access.ensure(Action.UPDATE)
    p = access.project
    changes = {}
    if body.slug is not None and body.slug != p.slug:
        if await slug_taken(session, p.group_id, body.slug, except_project=p.id):
            raise conflict("slug_taken")
        changes["slug"] = {"from": p.slug, "to": body.slug}
        p.slug = body.slug
    if body.name is not None and body.name != p.name:
        changes["name"] = {"from": p.name, "to": body.name}
        p.name = body.name
    if "description" in body.model_fields_set:
        p.description = body.description
    if changes:
        record(
            session,
            request,
            "project.updated",
            actor_user_id=access.user.id,
            project_id=p.id,
            group_id=p.group_id,
            resource_type="project",
            resource_id=p.id,
            details=changes,
        )
    await session.commit()
    return project_out(await load_project_access(session, access.user, p.id))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(access: ProjectAccessDep, request: Request, session: SessionDep) -> None:
    access.ensure(Action.DELETE)
    record(
        session,
        request,
        "project.deleted",
        actor_user_id=access.user.id,
        project_id=access.project.id,
        group_id=access.project.group_id,
        resource_type="project",
        resource_id=access.project.id,
        details={"path": access.path},
    )
    await session.delete(access.project)
    await session.commit()


# --- Members -----------------------------------------------------------------


@router.get("/{project_id}/members", response_model=list[members.MemberOut])
async def list_project_members(access: ProjectAccessDep, session: SessionDep):
    return await members.list_members(session, access)


@router.post(
    "/{project_id}/members", response_model=members.AddResult, status_code=status.HTTP_201_CREATED
)
async def add_project_member(
    body: members.MemberAdd, access: ProjectAccessDep, request: Request, session: SessionDep
):
    return await members.add_member(session, request, access, body)


@router.patch("/{project_id}/members/{member_id}", response_model=members.MemberOut)
async def update_project_member(
    member_id: uuid.UUID,
    body: members.MemberUpdate,
    access: ProjectAccessDep,
    request: Request,
    session: SessionDep,
):
    return await members.update_member(session, request, access, member_id, body)


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
    member_id: uuid.UUID, access: ProjectAccessDep, request: Request, session: SessionDep
) -> None:
    await members.remove_member(session, request, access, member_id)


@router.get("/{project_id}/invitations", response_model=list[members.InvitationOut])
async def list_project_invitations(access: ProjectAccessDep, session: SessionDep):
    return await members.list_invitations(session, access)


@router.delete("/{project_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_project_invitation(
    invitation_id: uuid.UUID, access: ProjectAccessDep, request: Request, session: SessionDep
) -> None:
    await members.revoke_invitation(session, request, access, invitation_id)
