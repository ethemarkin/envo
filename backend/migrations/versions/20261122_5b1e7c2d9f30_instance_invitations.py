"""instance invitations

Revision ID: 5b1e7c2d9f30
Revises: ecc5c486e576
Create Date: 2026-11-22 23:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

ROLE = postgresql.ENUM('owner', 'admin', 'developer', 'viewer', name='member_role', create_type=False)

revision: str = '5b1e7c2d9f30'
down_revision: str | None = 'ecc5c486e576'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Invitations without a group or project (sent by administrators) let
    # someone sign up to the instance; they carry no role.
    op.drop_constraint(op.f('ck_invitations_exactly_one_target'), 'invitations', type_='check')
    op.alter_column('invitations', 'role', existing_type=ROLE, nullable=True)
    op.create_check_constraint(
        op.f('ck_invitations_at_most_one_target'),
        'invitations',
        'group_id IS NULL OR project_id IS NULL',
    )
    op.create_check_constraint(
        op.f('ck_invitations_role_iff_target'),
        'invitations',
        '(group_id IS NULL AND project_id IS NULL) = (role IS NULL)',
    )


def downgrade() -> None:
    op.execute('DELETE FROM invitations WHERE group_id IS NULL AND project_id IS NULL')
    op.drop_constraint(op.f('ck_invitations_role_iff_target'), 'invitations', type_='check')
    op.drop_constraint(op.f('ck_invitations_at_most_one_target'), 'invitations', type_='check')
    op.alter_column('invitations', 'role', existing_type=ROLE, nullable=False)
    op.create_check_constraint(
        op.f('ck_invitations_exactly_one_target'),
        'invitations',
        '(group_id IS NULL) <> (project_id IS NULL)',
    )
