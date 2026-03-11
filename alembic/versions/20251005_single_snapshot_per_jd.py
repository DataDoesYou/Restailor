"""enforce single application snapshot per jd

Revision ID: 20251005_single_snapshot_per_jd
Revises: 20251001_snapshot_is_active_stub
Create Date: 2025-10-05 12:00:00
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20251005_single_snapshot_per_jd"
down_revision = "20251001_snapshot_is_active_stub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY user_id, jd_hash
                       ORDER BY is_applied DESC,
                                (job_id IS NOT NULL) DESC,
                                updated_at DESC,
                                created_at DESC,
                                id DESC
                   ) AS rn
            FROM applications
        )
        DELETE FROM applications a
        USING ranked r
        WHERE a.id = r.id
          AND r.rn > 1
        """
    )
    op.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS uq_applications_user_jd")
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd")
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd_canonical")
    op.execute(
        """
        UPDATE applications
        SET applied_key_canonical = applied_key
        WHERE applied_key_canonical IS DISTINCT FROM applied_key
        """
    )
    op.create_unique_constraint("uq_applications_user_jd", "applications", ["user_id", "jd_hash"])


def downgrade() -> None:
    op.drop_constraint("uq_applications_user_jd", "applications", type_="unique")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_user_jd_canonical ON applications (user_id, jd_hash) WHERE job_id IS NULL"
    )
