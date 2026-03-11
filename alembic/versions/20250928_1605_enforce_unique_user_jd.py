"""restore unique applications per user/jd pair

Revision ID: 20250928_enforce_app_user_jd
Revises: 20250928_drop_app_user_jd_index
Create Date: 2025-09-28 16:05:00
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20250928_enforce_app_user_jd"
down_revision = "20250928_drop_app_user_jd_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS uq_applications_user_jd")
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd")
    op.execute(
        """
        DELETE FROM applications
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY user_id, jd_hash
                           ORDER BY (job_id IS NOT NULL) DESC,
                                    is_applied DESC,
                                    updated_at DESC,
                                    created_at DESC,
                                    id DESC
                       ) AS rn
                FROM applications
                WHERE job_id IS NULL
            ) ranked
            WHERE rn > 1
        )
        """
    )
    op.execute(
        """
        UPDATE applications
        SET applied_key_canonical = split_part(applied_key, '#job:', 1)
        WHERE applied_key_canonical IS DISTINCT FROM split_part(applied_key, '#job:', 1)
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_user_jd_canonical ON applications (user_id, jd_hash) WHERE job_id IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd_canonical")
    op.execute(
        "ALTER TABLE applications ADD CONSTRAINT uq_applications_user_jd UNIQUE (user_id, jd_hash)"
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_user_jd ON applications (user_id, jd_hash)")
