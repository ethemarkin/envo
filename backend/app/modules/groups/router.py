import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import conflict, forbidden
from app.modules.audit_logs.service import record
from app.modules.authorization import members
from app.modules.authorization.access import can_create_root
from app.modules.authorization.deps import GroupAccess, GroupAccessDep, load_group_access
from app.modules.authorization.policy import Action, Role
from app.modules.groups.models import Group, GroupMember
from app.modules.groups.namespace import choose_slug, slug_taken
from app.modules.groups.schemas import BreadcrumbOut, ChildOut, GroupCreate, GroupOut, GroupUpdate
from app.modules.projects.models import Project

router = APIRouter(prefix="/api/groups", tags=["groups"])


def group_out(access: GroupAccess) -> GroupOut:
    g = access.group
    return GroupOut(
        id=g.id,
        parent_id=g.parent_id,
        name=g.name,
        slug=g.slug,
        path=access.path,
        description=g.description,
        role=access.role,
        ancestors=[
            BreadcrumbOut(id=a.id, name=a.name, slug=a.slug) for a in reversed(access.chain[1:])
        ],
        created_at=g.created_at,
    )


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupCreate, user: CurrentUser, request: Request, session: SessionDep):
    if body.parent_id is None:
        if not await can_create_root(session, user):
            raise forbidden("root_creation_disabled")
    else:
        parent = await load_group_access(session, user, body.parent_id)
        parent.ensure(Action.CREATE_CHILD)

    slug = await choose_slug(session, body.parent_id, body.slug, body.name, "group")
    group = Group(parent_id=body.parent_id, name=body.name, slug=slug, description=body.description)
    session.add(group)
    await session.flush()
    if body.parent_id is None:
        # Top-level groups start with their creator as owner; subgroups inherit.
        session.add(GroupMember(group_id=group.id, user_id=user.id, role=Role.OWNER))
    record(
        session,
        request,
        "group.created",
        actor_user_id=user.id,
        group_id=group.id,
        resource_type="group",
        resource_id=group.id,
        details={"slug": slug, "parent_id": str(body.parent_id) if body.parent_id else None},
    )
    await session.commit()
    return group_out(await load_group_access(session, user, group.id))


@router.get("/{group_id}", response_model=GroupOut)
async def get_group(access: GroupAccessDep):
    access.ensure(Action.READ)
    return group_out(access)


@router.get("/{group_id}/children", response_model=list[ChildOut])
async def list_children(access: GroupAccessDep, session: SessionDep):
    """Direct subgroups and projects. Anyone with a role on the group sees all
    children, since membership is inherited downwards."""
    access.ensure(Action.READ)
    gid = access.group.id
    subgroups = await session.scalars(
        select(Group).where(Group.parent_id == gid).order_by(Group.name)
    )
    projects = await session.scalars(
        select(Project).where(Project.group_id == gid).order_by(Project.name)
    )
    return [
        *(
            ChildOut(id=g.id, type="group", name=g.name, slug=g.slug, description=g.description)
            for g in subgroups
        ),
        *(
            ChildOut(id=p.id, type="project", name=p.name, slug=p.slug, description=p.description)
            for p in projects
        ),
    ]


@router.patch("/{group_id}", response_model=GroupOut)
async def update_group(
    body: GroupUpdate, access: GroupAccessDep, request: Request, session: SessionDep
):
    access.ensure(Action.UPDATE)
    g = access.group
    changes = {}
    if body.slug is not None and body.slug != g.slug:
        if await slug_taken(session, g.parent_id, body.slug, except_group=g.id):
            raise conflict("slug_taken")
        changes["slug"] = {"from": g.slug, "to": body.slug}
        g.slug = body.slug
    if body.name is not None and body.name != g.name:
        changes["name"] = {"from": g.name, "to": body.name}
        g.name = body.name
    if "description" in body.model_fields_set:
        g.description = body.description
    if changes:
        record(
            session,
            request,
            "group.updated",
            actor_user_id=access.user.id,
            group_id=g.id,
            resource_type="group",
            resource_id=g.id,
            details=changes,
        )
    await session.commit()
    return group_out(await load_group_access(session, access.user, g.id))


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(access: GroupAccessDep, request: Request, session: SessionDep) -> None:
    """Deletes the group with all subgroups, projects, environments and variables."""
    access.ensure(Action.DELETE)
    record(
        session,
        request,
        "group.deleted",
        actor_user_id=access.user.id,
        group_id=access.group.id,
        resource_type="group",
        resource_id=access.group.id,
        details={"path": access.path},
    )
    await session.delete(access.group)
    await session.commit()


# --- Members -----------------------------------------------------------------


@router.get("/{group_id}/members", response_model=list[members.MemberOut])
async def list_group_members(access: GroupAccessDep, session: SessionDep):
    return await members.list_members(session, access)


@router.post(
    "/{group_id}/members", response_model=members.AddResult, status_code=status.HTTP_201_CREATED
)
async def add_group_member(
    body: members.MemberAdd, access: GroupAccessDep, request: Request, session: SessionDep
):
    return await members.add_member(session, request, access, body)


@router.patch("/{group_id}/members/{member_id}", response_model=members.MemberOut)
async def update_group_member(
    member_id: uuid.UUID,
    body: members.MemberUpdate,
    access: GroupAccessDep,
    request: Request,
    session: SessionDep,
):
    return await members.update_member(session, request, access, member_id, body)


@router.delete("/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_member(
    member_id: uuid.UUID, access: GroupAccessDep, request: Request, session: SessionDep
) -> None:
    await members.remove_member(session, request, access, member_id)


@router.get("/{group_id}/invitations", response_model=list[members.InvitationOut])
async def list_group_invitations(access: GroupAccessDep, session: SessionDep):
    return await members.list_invitations(session, access)


@router.delete("/{group_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_group_invitation(
    invitation_id: uuid.UUID, access: GroupAccessDep, request: Request, session: SessionDep
) -> None:
    await members.revoke_invitation(session, request, access, invitation_id)
