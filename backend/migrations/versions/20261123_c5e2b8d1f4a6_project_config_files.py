"""project config files: files other than .env, e.g. application.properties

Revision ID: c5e2b8d1f4a6
Revises: a3d9e6f41c27
Create Date: 2026-11-23 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5e2b8d1f4a6"
down_revision: str | None = "a3d9e6f41c27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # project_env_files becomes project_files; existing rows are .env files.
    op.rename_table("project_env_files", "project_files")
    op.execute(
        "ALTER TABLE project_files RENAME CONSTRAINT pk_project_env_files TO pk_project_files"
    )
    op.execute(
        "ALTER TABLE project_files RENAME CONSTRAINT fk_project_env_files_project_id_projects "
        "TO fk_project_files_project_id_projects"
    )
    op.execute("ALTER INDEX ix_project_env_files_project_id RENAME TO ix_project_files_project_id")
    op.drop_constraint("uq_project_env_files_project_id_path", "project_files", type_="unique")
    op.add_column(
        "project_files",
        sa.Column("name", sa.String(length=255), server_default=".env", nullable=False),
    )
    op.create_unique_constraint(
        op.f("uq_project_files_project_id_path_name"),
        "project_files",
        ["project_id", "path", "name"],
    )


def downgrade() -> None:
    # Config file contents (keys "file:<name>") cannot be represented without them.
    op.execute("DELETE FROM variables WHERE key LIKE 'file:%'")
    op.execute("DELETE FROM variable_revisions WHERE key LIKE 'file:%'")
    op.execute("DELETE FROM project_files WHERE name <> '.env'")
    op.drop_constraint(
        op.f("uq_project_files_project_id_path_name"), "project_files", type_="unique"
    )
    op.drop_column("project_files", "name")
    op.create_unique_constraint(
        "uq_project_env_files_project_id_path", "project_files", ["project_id", "path"]
    )
    op.execute("ALTER INDEX ix_project_files_project_id RENAME TO ix_project_env_files_project_id")
    op.execute(
        "ALTER TABLE project_files RENAME CONSTRAINT fk_project_files_project_id_projects "
        "TO fk_project_env_files_project_id_projects"
    )
    op.execute(
        "ALTER TABLE project_files RENAME CONSTRAINT pk_project_files TO pk_project_env_files"
    )
    op.rename_table("project_files", "project_env_files")
