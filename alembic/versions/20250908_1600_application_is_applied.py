"""replace kind with is_applied boolean and enforce single row per (user,jd_hash)

Revision ID: 20250908_app_is_applied
Revises: 20250908_app_kind
Create Date: 2025-09-08 16:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250908_app_is_applied'
down_revision = '20250908_app_kind'
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c['name'] for c in insp.get_columns('applications')}
    has_is_applied = 'is_applied' in cols
    has_kind = 'kind' in cols

    # 1. Add is_applied if missing
    if not has_is_applied:
        op.add_column('applications', sa.Column('is_applied', sa.Boolean(), nullable=True))
        has_is_applied = True

    # Refresh columns after possible add
    if has_is_applied and has_kind:
        # 2. Backfill from kind only for rows where is_applied is null
        op.execute("UPDATE applications SET is_applied = (kind='applied') WHERE is_applied IS NULL")
    else:
        # Ensure any remaining NULLs become false
        op.execute("UPDATE applications SET is_applied = false WHERE is_applied IS NULL")

    # 3. Enforce NOT NULL + default
    op.alter_column('applications', 'is_applied', existing_type=sa.Boolean(), nullable=False, server_default=sa.text('false'))

    # 4. Deduplicate (safe to run multiple times)
    op.execute(
        """
        WITH ranked AS (
            SELECT id, user_id, jd_hash,
                   ROW_NUMBER() OVER (PARTITION BY user_id, jd_hash ORDER BY is_applied DESC, updated_at DESC, created_at DESC, id DESC) AS rn
            FROM applications
        )
        DELETE FROM applications a USING ranked r
        WHERE a.id = r.id AND r.rn > 1;
        """
    )

    # 5. Create unique index if not exists
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_user_jd ON applications (user_id, jd_hash)")

    # 6. Drop legacy indexes / column if still present
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd_history")
    op.execute("DROP INDEX IF EXISTS ix_applications_user_jd_applied")
    # Drop kind index then column conditionally
    if has_kind:
        try:
            op.drop_index('ix_applications_kind', table_name='applications')
        except Exception:
            pass  # index may already be gone
        # Re-inspect to ensure column still exists (wasn't manually dropped)
        cols_after = {c['name'] for c in insp.get_columns('applications')}
        if 'kind' in cols_after:
            try:
                op.drop_column('applications', 'kind')
            except Exception:
                pass


def downgrade() -> None:
    # Best-effort reversal: reintroduce kind='history'/'applied'
    op.add_column('applications', sa.Column('kind', sa.String(length=16), nullable=True))
    op.execute("UPDATE applications SET kind = CASE WHEN is_applied THEN 'applied' ELSE 'history' END")
    op.alter_column('applications', 'kind', existing_type=sa.String(length=16), nullable=False, server_default='history')
    op.create_index('ix_applications_kind', 'applications', ['kind'])
    # Recreate partial indexes (semantics approximate)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_user_jd_history ON applications (user_id, jd_hash) WHERE kind='history'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_applications_user_jd_applied ON applications (user_id, jd_hash) WHERE kind='applied'")
    # Drop new unique index + column
    op.drop_index('uq_applications_user_jd', table_name='applications')
    op.drop_column('applications', 'is_applied')
