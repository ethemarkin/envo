"""groups instead of organizations

Replaces organizations with nested groups (GitLab style) and moves
memberships to groups and projects. Existing data is converted:

- every organization becomes a top-level group with the same id, name and slug
- organization memberships become memberships of that group
- projects move into that group
- audit events keep their organization id as group id
- the earliest user becomes the instance administrator

Revision ID: 46d85c438727
Revises: 2805f12a781b
Create Date: 2026-11-22 19:25:27.696189
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "46d85c438727"
down_revision: str | None = "2805f12a781b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

member_role = postgresql.ENUM(
    "owner", "admin", "developer", "viewer", name="member_role", create_type=False
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    # --- Instance administration
    op.add_column(
        "users", sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.execute(
        "UPDATE users SET is_admin = true "
        "WHERE id = (SELECT id FROM users ORDER BY created_at, id LIMIT 1)"
    )
    op.create_table(
        "instance_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("allow_root_creation", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("id = 1", name=op.f("ck_instance_settings_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instance_settings")),
    )
    op.execute("INSERT INTO instance_settings (id, allow_root_creation) VALUES (1, true)")

    # --- Groups
    op.create_table(
        "groups",
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["groups.id"], name=op.f("fk_groups_parent_id_groups"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_groups")),
    )
    op.create_index(op.f("ix_groups_parent_id"), "groups", ["parent_id"])
    op.create_index(
        "uq_groups_root_slug", "groups", ["slug"], unique=True,
        postgresql_where=sa.text("parent_id IS NULL"),
    )
    op.create_index(
        "uq_groups_parent_slug", "groups", ["parent_id", "slug"], unique=True,
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )
    op.execute(
        "INSERT INTO groups (id, parent_id, name, slug, created_at, updated_at) "
        "SELECT id, NULL, name, slug, created_at, updated_at FROM organizations"
    )

    op.create_table(
        "group_members",
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", member_role, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["group_id"], ["groups.id"], name=op.f("fk_group_members_group_id_groups"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_group_members_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_group_members")),
        sa.UniqueConstraint("group_id", "user_id", name=op.f("uq_group_members_group_id_user_id")),
    )
    op.create_index(op.f("ix_group_members_user_id"), "group_members", ["user_id"])
    op.execute(
        "INSERT INTO group_members (id, group_id, user_id, role, created_at, updated_at) "
        "SELECT id, organization_id, user_id, role, created_at, updated_at FROM memberships"
    )

    # --- Projects: organization -> group, plus direct project members
    op.add_column("projects", sa.Column("group_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE projects SET group_id = organization_id")
    op.drop_constraint("uq_projects_organization_id_slug", "projects", type_="unique")
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_constraint("fk_projects_organization_id_organizations", "projects", type_="foreignkey")
    op.drop_column("projects", "organization_id")
    op.create_foreign_key(
        op.f("fk_projects_group_id_groups"), "projects", "groups", ["group_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_projects_group_id"), "projects", ["group_id"])
    op.create_index(
        "uq_projects_root_slug", "projects", ["slug"], unique=True,
        postgresql_where=sa.text("group_id IS NULL"),
    )
    op.create_index(
        "uq_projects_group_slug", "projects", ["group_id", "slug"], unique=True,
        postgresql_where=sa.text("group_id IS NOT NULL"),
    )

    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", member_role, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_project_members_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_project_members_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_members")),
        sa.UniqueConstraint("project_id", "user_id", name=op.f("uq_project_members_project_id_user_id")),
    )
    op.create_index(op.f("ix_project_members_user_id"), "project_members", ["user_id"])

    # --- Audit events: keep the trail, without foreign keys
    op.add_column("audit_events", sa.Column("group_id", sa.Uuid(), nullable=True))
    op.add_column("audit_events", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE audit_events SET group_id = organization_id")
    op.execute(
        "UPDATE audit_events SET project_id = (details->>'project_id')::uuid "
        "WHERE details ? 'project_id'"
    )
    op.drop_index("ix_audit_events_organization_id", table_name="audit_events")
    op.drop_constraint(
        "fk_audit_events_organization_id_organizations", "audit_events", type_="foreignkey"
    )
    op.drop_column("audit_events", "organization_id")
    op.create_index(op.f("ix_audit_events_project_id"), "audit_events", ["project_id", "created_at"])
    op.create_index(op.f("ix_audit_events_group_id"), "audit_events", ["group_id", "created_at"])

    # --- Organizations are gone
    op.drop_table("memberships")
    op.drop_table("organizations")


def downgrade() -> None:
    raise NotImplementedError(
        "Converting nested groups back into flat organizations is lossy; restore a backup instead."
    )
