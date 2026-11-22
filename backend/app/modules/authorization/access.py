"""Effective roles with GitLab-style inheritance.

A user's role on a group is the highest of their direct membership there and
on every ancestor group. A project adds its own direct members on top of its
group chain. Instance administrators are owners everywhere.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models import SETTINGS_ID, InstanceSettings
from app.modules.auth.models import User
from app.modules.authorization.policy import Role, highest
from app.modules.groups.models import Group, GroupMember
from app.modules.projects.models import Project, ProjectMember


async def ancestor_chain(session: AsyncSession, group_id: uuid.UUID | None) -> list[Group]:
    """The group and its ancestors, nearest first. Empty for None."""
    if group_id is None:
        return []
    base = select(Group.id, Group.parent_id, literal(0).label("depth")).where(Group.id == group_id)
    chain = base.cte("chain", recursive=True)
    chain = chain.union_all(
        select(Group.id, Group.parent_id, (chain.c.depth + 1).label("depth")).join(
            chain, Group.id == chain.c.parent_id
        )
    )
    rows = await session.execute(
        select(Group).join(chain, Group.id == chain.c.id).order_by(chain.c.depth)
    )
    return list(rows.scalars())


def path_of(chain: list[Group], leaf_slug: str | None = None) -> str:
    """Full path like "acme/backend/web-api" from an ancestor chain (nearest first)."""
    parts = [g.slug for g in reversed(chain)]
    if leaf_slug is not None:
        parts.append(leaf_slug)
    return "/".join(parts)


async def _group_roles(session: AsyncSession, user: User, group_ids: list[uuid.UUID]) -> list[Role]:
    if not group_ids:
        return []
    rows = await session.scalars(
        select(GroupMember.role).where(
            GroupMember.user_id == user.id, GroupMember.group_id.in_(group_ids)
        )
    )
    return list(rows)


async def group_role(session: AsyncSession, user: User, chain: list[Group]) -> Role | None:
    if user.is_admin:
        return Role.OWNER
    return highest(await _group_roles(session, user, [g.id for g in chain]))


async def project_role(
    session: AsyncSession, user: User, project: Project, chain: list[Group]
) -> Role | None:
    if user.is_admin:
        return Role.OWNER
    direct = await session.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    )
    return highest([direct, *await _group_roles(session, user, [g.id for g in chain])])


async def get_settings_row(session: AsyncSession) -> InstanceSettings:
    row = await session.get(InstanceSettings, SETTINGS_ID)
    if row is None:
        row = InstanceSettings(id=SETTINGS_ID, allow_root_creation=True)
        session.add(row)
        await session.flush()
    return row


async def can_create_root(session: AsyncSession, user: User) -> bool:
    return user.is_admin or (await get_settings_row(session)).allow_root_creation


# --- Visible tree -------------------------------------------------------------


@dataclass
class TreeNode:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    slug: str
    path: str
    role: Role | None  # None: only shown as the path to something accessible


@dataclass
class VisibleTree:
    groups: list[TreeNode] = field(default_factory=list)
    projects: list[TreeNode] = field(default_factory=list)


async def visible_tree(session: AsyncSession, user: User) -> VisibleTree:
    """Groups and projects the user can access, plus the ancestor groups
    needed to place them in the tree.

    Loads the whole hierarchy (ids, names, slugs) once and resolves roles in
    memory; fine for the instance sizes Envo targets.
    """
    groups = {g.id: g for g in await session.scalars(select(Group))}
    projects = list(await session.scalars(select(Project)))
    group_rows = await session.execute(
        select(GroupMember.group_id, GroupMember.role).where(GroupMember.user_id == user.id)
    )
    group_direct = {gid: role for gid, role in group_rows}
    project_rows = await session.execute(
        select(ProjectMember.project_id, ProjectMember.role).where(ProjectMember.user_id == user.id)
    )
    project_direct = {pid: role for pid, role in project_rows}

    role_cache: dict[uuid.UUID, Role | None] = {}
    path_cache: dict[uuid.UUID, str] = {}

    def g_role(gid: uuid.UUID) -> Role | None:
        if gid not in role_cache:
            g = groups[gid]
            parent = g_role(g.parent_id) if g.parent_id else None
            inherited = highest([group_direct.get(gid), parent])
            role_cache[gid] = Role.OWNER if user.is_admin else inherited
        return role_cache[gid]

    def g_path(gid: uuid.UUID) -> str:
        if gid not in path_cache:
            g = groups[gid]
            path_cache[gid] = f"{g_path(g.parent_id)}/{g.slug}" if g.parent_id else g.slug
        return path_cache[gid]

    shown: set[uuid.UUID] = set()

    def show_with_ancestors(gid: uuid.UUID | None) -> None:
        while gid is not None and gid not in shown:
            shown.add(gid)
            gid = groups[gid].parent_id

    tree = VisibleTree()
    for p in projects:
        role = (
            Role.OWNER
            if user.is_admin
            else highest([project_direct.get(p.id), g_role(p.group_id) if p.group_id else None])
        )
        if role is None:
            continue
        show_with_ancestors(p.group_id)
        path = f"{g_path(p.group_id)}/{p.slug}" if p.group_id else p.slug
        tree.projects.append(TreeNode(p.id, p.group_id, p.name, p.slug, path, role))
    for gid in groups:
        if g_role(gid) is not None:
            show_with_ancestors(gid)
    for gid in shown:
        g = groups[gid]
        tree.groups.append(TreeNode(g.id, g.parent_id, g.name, g.slug, g_path(gid), g_role(gid)))

    tree.groups.sort(key=lambda n: n.path)
    tree.projects.sort(key=lambda n: n.path)
    return tree
