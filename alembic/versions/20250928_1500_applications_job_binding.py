"""bind applications to jobs for analytics stage recovery

Revision ID: 20250928_app_job_binding
Revises: 20250928_drop_job_stage_flags
Create Date: 2025-09-28 15:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20250928_app_job_binding"
down_revision = "20250928_drop_job_stage_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS uq_applications_user_jd")
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd")
    op.add_column(
        "applications",
        sa.Column("applied_key_canonical", sa.Text(), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_applications_job_id_jobs",
        "applications",
        "jobs",
        ["job_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute("UPDATE applications SET applied_key_canonical = applied_key WHERE applied_key_canonical IS NULL")
    op.create_index(
        "ix_applications_applied_key_canonical",
        "applications",
        ["applied_key_canonical"],
        unique=False,
    )
    op.create_index(
        "ix_applications_job_id_not_null_unique",
        "applications",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("job_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_user_jd ON applications (user_id, jd_hash)")
    op.drop_index("ix_applications_job_id_not_null_unique", table_name="applications")
    op.drop_index("ix_applications_applied_key_canonical", table_name="applications")
    op.drop_constraint("fk_applications_job_id_jobs", "applications", type_="foreignkey")
    op.drop_column("applications", "job_id")
    op.drop_column("applications", "applied_key_canonical")
