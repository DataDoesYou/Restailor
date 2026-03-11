"""add independent stage flags to jobs (interviewing/offer/hired)

Revision ID: 20250925_0900_stage_flags
Revises: 20250920_2000_jobs_indexes_perf
Create Date: 2025-09-25 09:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250925_0900_stage_flags"
down_revision = "20250920_2000_jobs_indexes_perf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new boolean columns with defaults for safe backfill
    op.add_column("jobs", sa.Column("has_interviewing", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("jobs", sa.Column("has_offer", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("jobs", sa.Column("has_hired", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    # Indexes to accelerate filters/sorts in history
    try:
        op.create_index("ix_jobs_has_interviewing", "jobs", ["has_interviewing"], unique=False)
    except Exception:
        pass
    try:
        op.create_index("ix_jobs_has_offer", "jobs", ["has_offer"], unique=False)
    except Exception:
        pass
    try:
        op.create_index("ix_jobs_has_hired", "jobs", ["has_hired"], unique=False)
    except Exception:
        pass


def downgrade() -> None:
    # Drop indexes first
    for idx in ("ix_jobs_has_hired", "ix_jobs_has_offer", "ix_jobs_has_interviewing"):
        try:
            op.drop_index(idx, table_name="jobs")
        except Exception:
            pass
    # Then drop columns
    with op.batch_alter_table("jobs") as batch_op:
        for col in ("has_hired", "has_offer", "has_interviewing"):
            try:
                batch_op.drop_column(col)
            except Exception:
                pass
