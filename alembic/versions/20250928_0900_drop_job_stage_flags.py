"""drop job stage flag columns in favor of application state

Revision ID: 20250928_drop_job_stage_flags
Revises: 20250927_drop_stage_columns
Create Date: 2025-09-28 09:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250928_drop_job_stage_flags"
down_revision = "20250927_drop_stage_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for index_name in ("ix_jobs_has_interviewing", "ix_jobs_has_offer", "ix_jobs_has_hired"):
        try:
            op.drop_index(index_name, table_name="jobs")
        except Exception:
            pass

    with op.batch_alter_table("jobs") as batch_op:
        for column_name in ("has_interviewing", "has_offer", "has_hired"):
            try:
                batch_op.drop_column(column_name)
            except Exception:
                pass


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        for column_name in ("has_interviewing", "has_offer", "has_hired"):
            batch_op.add_column(
                sa.Column(column_name, sa.Boolean(), nullable=False, server_default=sa.text("false"))
            )

    for index_name, column_name in (
        ("ix_jobs_has_interviewing", "has_interviewing"),
        ("ix_jobs_has_offer", "has_offer"),
        ("ix_jobs_has_hired", "has_hired"),
    ):
        try:
            op.create_index(index_name, "jobs", [column_name], unique=False)
        except Exception:
            pass
