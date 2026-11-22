import pytest

from app.modules.authorization.policy import (
    POLICY,
    Action,
    Role,
    can,
    can_assign_role,
    highest,
)

O, A, D, V = Role.OWNER, Role.ADMIN, Role.DEVELOPER, Role.VIEWER

# Mirrors the role matrix in MVP_PLAN.md for group and project actions.
EXPECTED = {
    Action.READ: {O, A, D, V},
    Action.UPDATE: {O, A},
    Action.DELETE: {O},
    Action.MEMBER_READ: {O, A, D, V},
    Action.MEMBER_MANAGE: {O, A},
    Action.CREATE_CHILD: {O, A},
    Action.ENVIRONMENT_MANAGE: {O, A},
}


def test_highest_role_wins():
    assert highest([V, None, D]) == D
    assert highest([A, O, V]) == O
    assert highest([None, None]) is None
    assert highest([]) is None


def test_every_action_has_a_rule():
    assert set(POLICY) == set(Action) == set(EXPECTED)


@pytest.mark.parametrize("action", list(Action))
@pytest.mark.parametrize("role", list(Role))
def test_matrix(role, action):
    assert can(role, action) is (role in EXPECTED[action])


@pytest.mark.parametrize(
    ("actor", "current", "new", "allowed"),
    [
        (O, D, O, True),
        (O, O, A, True),
        (A, D, V, True),
        (A, D, O, False),
        (A, O, A, False),
        (A, O, None, False),
        (A, None, D, True),
        (D, V, D, False),
        (V, None, V, False),
    ],
)
def test_role_assignment(actor, current, new, allowed):
    assert can_assign_role(actor, current, new) is allowed
