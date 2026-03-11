"""jobs performance indexes for list and stage filters

Revision ID: 20250920_2000_jobs_indexes_perf
Revises: 20250920_jobs_stage_del
Create Date: 2025-09-20 20:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250920_2000_jobs_indexes_perf"
down_revision = "20250920_jobs_stage_del"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Accelerate lookups by (user_id, input_hash) where not deleted, used by applications list
    try:
        op.create_index(
            "ix_jobs_user_inputhash_not_deleted",
            "jobs",
            ["user_id", "input_hash"],
            unique=False,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    except Exception:
        pass

    # Improve stage counts filtered by user where not deleted
    # Note: we already have (stage, user_id) partial; add (user_id, stage) for user-scoped scans
    try:
        op.create_index(
            "ix_jobs_user_stage_not_deleted",
            "jobs",
            ["user_id", "stage"],
            unique=False,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_index("ix_jobs_user_inputhash_not_deleted", table_name="jobs")
    except Exception:
        pass
    try:
        op.drop_index("ix_jobs_user_stage_not_deleted", table_name="jobs")
    except Exception:
        pass
