"""Resolve the group or project in the URL together with the caller's
effective role. Without any role the resource yields 404, not 403, so
inaccessible groups and projects are not even confirmed to exist.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import forbidden, not_found
from app.modules.auth.models import User
from app.modules.authorization.access import (
    ancestor_chain,
    group_role,
    path_of,
    project_role,
)
from app.modules.authorization.policy import Action, Role, can
from app.modules.groups.models import Group
from app.modules.projects.models import Project


@dataclass
class GroupAccess:
    group: Group
    chain: list[Group]  # the group and its ancestors, nearest first
    role: Role
    user: User

    @property
    def path(self) -> str:
        return path_of(self.chain)

    def ensure(self, action: Action) -> None:
        if not can(self.role, action):
            raise forbidden()


@dataclass
class ProjectAccess:
    project: Project
    chain: list[Group]  # the project's group and its ancestors
    role: Role
    user: User

    @property
    def path(self) -> str:
        return path_of(self.chain, self.project.slug)

    @property
    def root_group_id(self) -> uuid.UUID | None:
        return self.chain[-1].id if self.chain else None

    def ensure(self, action: Action) -> None:
        if not can(self.role, action):
            raise forbidden()


async def load_group_access(session, user: User, group_id: uuid.UUID) -> GroupAccess:
    chain = await ancestor_chain(session, group_id)
    role = await group_role(session, user, chain) if chain else None
    if role is None:
        raise not_found("group_not_found")
    return GroupAccess(chain[0], chain, role, user)


async def load_project_access(session, user: User, project_id: uuid.UUID) -> ProjectAccess:
    project = await session.get(Project, project_id)
    if project is None:
        raise not_found("project_not_found")
    chain = await ancestor_chain(session, project.group_id)
    role = await project_role(session, user, project, chain)
    if role is None:
        raise not_found("project_not_found")
    return ProjectAccess(project, chain, role, user)


async def group_access(group_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> GroupAccess:
    return await load_group_access(session, user, group_id)


async def project_access(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ProjectAccess:
    return await load_project_access(session, user, project_id)


GroupAccessDep = Annotated[GroupAccess, Depends(group_access)]
ProjectAccessDep = Annotated[ProjectAccess, Depends(project_access)]
