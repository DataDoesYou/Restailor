"""add users table and job owner relationship; add user roles

Revision ID: 20250821_0110
Revises: add_client_id_0110
Create Date: 2025-08-21 01:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250821_0110"
down_revision = "add_active_job_guard_0120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # Add user_id to jobs as nullable FK; use SET NULL on delete
    op.add_column("jobs", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_jobs_user_id_users",
        "jobs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop FK and column
    op.drop_constraint("fk_jobs_user_id_users", "jobs", type_="foreignkey")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    op.drop_column("jobs", "user_id")

    # Drop users table
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
