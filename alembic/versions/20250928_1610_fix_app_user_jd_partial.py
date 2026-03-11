"""ensure applications user/jd uniqueness only applies to canonical rows

Revision ID: 20250928_fix_app_user_jd_partial
Revises: 20250928_enforce_app_user_jd
Create Date: 2025-09-28 16:10:00
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20250928_fix_app_user_jd_partial"
down_revision = "20250928_enforce_app_user_jd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS uq_applications_user_jd")
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd")
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd_canonical")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_user_jd_canonical ON applications (user_id, jd_hash) WHERE job_id IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd_canonical")
    op.execute(
        "ALTER TABLE applications ADD CONSTRAINT uq_applications_user_jd UNIQUE (user_id, jd_hash)"
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_user_jd ON applications (user_id, jd_hash)")
