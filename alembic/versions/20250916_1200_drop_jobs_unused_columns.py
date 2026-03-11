"""drop unused columns on jobs (cost, request_group_id, output_models, input_models)

Revision ID: 20250916_1200_drop_job_cols
Revises: 20250914_1805
Create Date: 2025-09-16 12:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250916_1200_drop_job_cols"
down_revision = "20250914_1805"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop index on request_group_id if present, then drop columns
    try:
        op.drop_index("ix_jobs_request_group_id", table_name="jobs")
    except Exception:
        # tolerate if index doesn't exist
        pass
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("request_group_id")
        batch_op.drop_column("output_models")
        batch_op.drop_column("input_models")
        batch_op.drop_column("cost")


def downgrade() -> None:
    # Recreate columns with original types (nullable)
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("cost", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("input_models", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("output_models", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("request_group_id", postgresql.UUID(as_uuid=True), nullable=True))
    # Recreate index on request_group_id
    try:
        op.create_index("ix_jobs_request_group_id", "jobs", ["request_group_id"])
    except Exception:
        pass
