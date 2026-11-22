"""Central authorization policy.

Every endpoint asks `can(role, action)` instead of comparing roles inline, so
the role matrix in MVP_PLAN.md lives in exactly one place and can be tested
as a table.
"""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class Action(StrEnum):
    ORG_READ = "org.read"
    ORG_UPDATE = "org.update"
    ORG_DELETE = "org.delete"
    MEMBER_READ = "member.read"
    MEMBER_MANAGE = "member.manage"
    PROJECT_READ = "project.read"
    PROJECT_MANAGE = "project.manage"
    ENVIRONMENT_READ = "environment.read"
    ENVIRONMENT_MANAGE = "environment.manage"


_ALL = frozenset(Role)
_ADMINS = frozenset({Role.OWNER, Role.ADMIN})

POLICY: dict[Action, frozenset[Role]] = {
    Action.ORG_READ: _ALL,
    Action.ORG_UPDATE: frozenset({Role.OWNER}),
    Action.ORG_DELETE: frozenset({Role.OWNER}),
    Action.MEMBER_READ: _ALL,
    Action.MEMBER_MANAGE: _ADMINS,
    Action.PROJECT_READ: _ALL,
    Action.PROJECT_MANAGE: _ADMINS,
    Action.ENVIRONMENT_READ: _ALL,
    Action.ENVIRONMENT_MANAGE: _ADMINS,
}


def can(role: Role, action: Action) -> bool:
    return role in POLICY[action]


def can_assign_role(actor: Role, target_current: Role | None, target_new: Role | None) -> bool:
    """Whether `actor` may change a member from `target_current` to `target_new`.

    None stands for "not a member" (invite / removal). Only owners may grant,
    change or remove the owner role.
    """
    if not can(actor, Action.MEMBER_MANAGE):
        return False
    if Role.OWNER in (target_current, target_new):
        return actor == Role.OWNER
    return True
