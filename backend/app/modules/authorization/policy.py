"""Central authorization policy.

Every endpoint asks `can(role, action)` instead of comparing roles inline, so
the role matrix in MVP_PLAN.md lives in exactly one place and can be tested
as a table.
"""

from collections.abc import Iterable
from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


# Higher wins when roles are inherited from several levels.
ROLE_RANK = {Role.VIEWER: 1, Role.DEVELOPER: 2, Role.ADMIN: 3, Role.OWNER: 4}


def highest(roles: Iterable[Role | None]) -> Role | None:
    present = [r for r in roles if r is not None]
    return max(present, key=ROLE_RANK.__getitem__) if present else None


class Action(StrEnum):
    """Actions on a group or project, checked against the caller's effective
    role there (direct membership or inherited from a parent group)."""

    READ = "read"
    UPDATE = "update"  # rename, change slug or description
    DELETE = "delete"
    MEMBER_READ = "member.read"
    MEMBER_MANAGE = "member.manage"
    CREATE_CHILD = "create_child"  # subgroups and projects inside a group
    ENVIRONMENT_MANAGE = "environment.manage"
    SERVICE_TOKEN_MANAGE = "service_token.manage"  # noqa: S105 (an action name)
    AUDIT_READ = "audit.read"


_ALL = frozenset(Role)
_ADMINS = frozenset({Role.OWNER, Role.ADMIN})

POLICY: dict[Action, frozenset[Role]] = {
    Action.READ: _ALL,
    Action.UPDATE: _ADMINS,
    Action.DELETE: frozenset({Role.OWNER}),
    Action.MEMBER_READ: _ALL,
    Action.MEMBER_MANAGE: _ADMINS,
    Action.CREATE_CHILD: _ADMINS,
    Action.ENVIRONMENT_MANAGE: _ADMINS,
    Action.SERVICE_TOKEN_MANAGE: _ADMINS,
    Action.AUDIT_READ: _ADMINS,
}


def can(role: Role, action: Action) -> bool:
    return role in POLICY[action]


class EnvAction(StrEnum):
    """Actions on variables, which also depend on the environment's protection."""

    LIST = "variables.list"  # keys and visible values
    READ_SECRETS = "variables.read_secrets"  # reveal, export, pull, run
    WRITE = "variables.write"  # set, import, delete, rollback


_DEVS = frozenset({Role.OWNER, Role.ADMIN, Role.DEVELOPER})

# action -> (roles on unprotected environments, roles on protected environments)
ENV_POLICY: dict[EnvAction, tuple[frozenset[Role], frozenset[Role]]] = {
    EnvAction.LIST: (_ALL, _ALL),
    EnvAction.READ_SECRETS: (_DEVS, _ADMINS),
    EnvAction.WRITE: (_DEVS, _ADMINS),
}


def can_env(role: Role, action: EnvAction, protected: bool) -> bool:
    unprotected_roles, protected_roles = ENV_POLICY[action]
    return role in (protected_roles if protected else unprotected_roles)


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
