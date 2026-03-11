"""add stage/archive flags to jobs

Revision ID: 20250920_0900_add_stage_archive
Revises: 20250916_1300_merge
Create Date: 2025-09-20 09:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250920_0900_add_stage_archive"
down_revision = "20250916_1300_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns with defaults
    op.add_column(
        "jobs",
        sa.Column("is_staged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "jobs",
        sa.Column("staged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "jobs",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Create simple indexes for filters
    op.create_index("ix_jobs_is_staged", "jobs", ["is_staged"], unique=False)
    op.create_index("ix_jobs_is_archived", "jobs", ["is_archived"], unique=False)


def downgrade() -> None:
    # Drop indexes first, then columns
    try:
        op.drop_index("ix_jobs_is_archived", table_name="jobs")
    except Exception:
        pass
    try:
        op.drop_index("ix_jobs_is_staged", table_name="jobs")
    except Exception:
        pass
    with op.batch_alter_table("jobs") as batch_op:
        try:
            batch_op.drop_column("archived_at")
        except Exception:
            pass
        try:
            batch_op.drop_column("is_archived")
        except Exception:
            pass
        try:
            batch_op.drop_column("staged_at")
        except Exception:
            pass
        try:
            batch_op.drop_column("is_staged")
        except Exception:
            pass
