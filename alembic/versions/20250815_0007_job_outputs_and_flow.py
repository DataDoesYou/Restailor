"""job outputs table and job_flow; drop jobs.result

Revision ID: 20250815_0007
Revises: 20250814_0006
Create Date: 2025-08-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250815_0007"
down_revision = "add_exports_audit_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add job_flow to jobs
    op.add_column("jobs", sa.Column("job_flow", sa.String(length=20), nullable=True))
    op.create_index("ix_jobs_job_flow", "jobs", ["job_flow"], unique=False)

    # Create job_outputs
    op.create_table(
        "job_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("content_enc", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_job_outputs_job_id", "job_outputs", ["job_id"], unique=False)
    op.create_index("ix_job_outputs_type", "job_outputs", ["type"], unique=False)
    op.create_index("ix_job_outputs_job_type_created", "job_outputs", ["job_id", "type", "created_at"], unique=False)

    # Drop ambiguous result column if exists
    with op.batch_alter_table("jobs") as batch_op:
        try:
            batch_op.drop_column("result")
        except Exception:
            pass


def downgrade() -> None:
    # Recreate result column (nullable)
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("result", sa.LargeBinary(), nullable=True))

    op.drop_index("ix_job_outputs_job_type_created", table_name="job_outputs")
    op.drop_index("ix_job_outputs_type", table_name="job_outputs")
    op.drop_index("ix_job_outputs_job_id", table_name="job_outputs")
    op.drop_table("job_outputs")

    op.drop_index("ix_jobs_job_flow", table_name="jobs")
    op.drop_column("jobs", "job_flow")
