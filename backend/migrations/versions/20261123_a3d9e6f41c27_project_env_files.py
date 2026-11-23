"""project env files: a .env only where the project places one

Revision ID: a3d9e6f41c27
Revises: 8c4f1a7e2b90
Create Date: 2026-11-23 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3d9e6f41c27'
down_revision: str | None = '8c4f1a7e2b90'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'project_env_files',
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_env_files_project_id_projects'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_project_env_files')),
        sa.UniqueConstraint('project_id', 'path', name=op.f('uq_project_env_files_project_id_path')),
    )
    op.create_index(op.f('ix_project_env_files_project_id'), 'project_env_files', ['project_id'], unique=False)

    # Until now every folder had a .env. Keep one at the root of every
    # project and wherever an environment holds values; empty folders
    # become structure only.
    op.execute(
        """
        INSERT INTO project_env_files (id, project_id, path)
        SELECT gen_random_uuid(), p.id, '' FROM projects p
        UNION ALL
        SELECT gen_random_uuid(), e.project_id, v.path
        FROM variables v JOIN environments e ON e.id = v.environment_id
        WHERE v.path <> ''
        GROUP BY e.project_id, v.path
        """
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_project_env_files_project_id'), table_name='project_env_files')
    op.drop_table('project_env_files')
