"""add jobs stage and deleted_at

Revision ID: 20250920_jobs_stage_del
Revises: 20250920_0900_add_stage_archive
Create Date: 2025-09-20 12:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250920_jobs_stage_del"  # <= 32 chars
down_revision = "20250920_0900_add_stage_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add stage TEXT NULL with CHECK constraint
    op.add_column("jobs", sa.Column("stage", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_jobs_stage_valid",
        "jobs",
        sa.text("stage IS NULL OR stage IN ('applied','interviewing','offer','hired')"),
    )

    # 2) Add deleted_at TIMESTAMPTZ NULL
    op.add_column("jobs", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # 3) Partial indexes
    op.create_index(
        "ix_jobs_user_id_not_deleted",
        "jobs",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_jobs_user_id_deleted",
        "jobs",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.create_index(
        "ix_jobs_stage_user_not_deleted",
        "jobs",
        ["stage", "user_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    # Drop partial indexes
    try:
        op.drop_index("ix_jobs_stage_user_not_deleted", table_name="jobs")
    except Exception:
        pass
    try:
        op.drop_index("ix_jobs_user_id_deleted", table_name="jobs")
    except Exception:
        pass
    try:
        op.drop_index("ix_jobs_user_id_not_deleted", table_name="jobs")
    except Exception:
        pass

    # Drop CHECK constraint then columns
    try:
        op.drop_constraint("ck_jobs_stage_valid", "jobs", type_="check")
    except Exception:
        pass

    with op.batch_alter_table("jobs") as batch_op:
        try:
            batch_op.drop_column("deleted_at")
        except Exception:
            pass
        try:
            batch_op.drop_column("stage")
        except Exception:
            pass
