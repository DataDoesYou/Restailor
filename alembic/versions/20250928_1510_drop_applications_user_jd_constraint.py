"""drop legacy unique constraint on applications user/jd

Revision ID: 20250928_drop_app_user_jd
Revises: 20250928_app_job_binding
Create Date: 2025-09-28 15:10:00
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20250928_drop_app_user_jd"
down_revision = "20250928_app_job_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS uq_applications_user_jd")
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE applications ADD CONSTRAINT uq_applications_user_jd UNIQUE (user_id, jd_hash)"
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_user_jd ON applications (user_id, jd_hash)")
