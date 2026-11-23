"""project folders: one .env per folder and environment

Revision ID: 8c4f1a7e2b90
Revises: 5b1e7c2d9f30
Create Date: 2026-11-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '8c4f1a7e2b90'
down_revision: str | None = '5b1e7c2d9f30'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'project_folders',
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_folders_project_id_projects'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_project_folders')),
        sa.UniqueConstraint('project_id', 'path', name=op.f('uq_project_folders_project_id_path')),
    )
    op.create_index(op.f('ix_project_folders_project_id'), 'project_folders', ['project_id'], unique=False)

    # Existing variables live in the project root ("").
    op.add_column('variables', sa.Column('path', sa.String(length=255), server_default='', nullable=False))
    op.drop_constraint(op.f('uq_variables_environment_id_key'), 'variables', type_='unique')
    op.create_unique_constraint(op.f('uq_variables_environment_id_path_key'), 'variables', ['environment_id', 'path', 'key'])

    op.add_column('variable_revisions', sa.Column('path', sa.String(length=255), server_default='', nullable=False))
    op.drop_index(op.f('ix_variable_revisions_environment_id'), table_name='variable_revisions')
    op.create_index(op.f('ix_variable_revisions_environment_id'), 'variable_revisions', ['environment_id', 'path', 'key', 'revision'], unique=False)


def downgrade() -> None:
    # Values outside the root cannot be represented without folders.
    op.execute("DELETE FROM variables WHERE path <> ''")
    op.execute("DELETE FROM variable_revisions WHERE path <> ''")
    op.drop_index(op.f('ix_variable_revisions_environment_id'), table_name='variable_revisions')
    op.create_index(op.f('ix_variable_revisions_environment_id'), 'variable_revisions', ['environment_id', 'key', 'revision'], unique=False)
    op.drop_column('variable_revisions', 'path')

    op.drop_constraint(op.f('uq_variables_environment_id_path_key'), 'variables', type_='unique')
    op.create_unique_constraint(op.f('uq_variables_environment_id_key'), 'variables', ['environment_id', 'key'])
    op.drop_column('variables', 'path')

    op.drop_index(op.f('ix_project_folders_project_id'), table_name='project_folders')
    op.drop_table('project_folders')
