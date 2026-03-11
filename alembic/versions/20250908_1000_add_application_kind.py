"""add application kind column

Revision ID: 20250908_app_kind
Revises: 20250907_0100_applications
Create Date: 2025-09-08 10:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250908_app_kind'
down_revision = '20250907_0100_applications'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add kind column with default 'history'; existing rows will be considered 'applied' logically
    # but we mark them 'applied' explicitly after adding the column.
    op.add_column('applications', sa.Column('kind', sa.String(length=16), nullable=True))
    # Backfill existing rows as 'applied'
    op.execute("UPDATE applications SET kind='applied' WHERE kind IS NULL")
    # Set non-null constraint + default
    op.alter_column('applications', 'kind', existing_type=sa.String(length=16), nullable=False, server_default='history')
    # Index for filtering
    op.create_index('ix_applications_kind', 'applications', ['kind'])
    # Partial unique index (PostgreSQL) to enforce one history snapshot per (user_id, jd_hash)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_user_jd_history ON applications (user_id, jd_hash) WHERE kind='history'")
    # Optional supporting index for applied lookups (user,jd_hash) when kind='applied'
    op.execute("CREATE INDEX IF NOT EXISTS ix_applications_user_jd_applied ON applications (user_id, jd_hash) WHERE kind='applied'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_applications_user_jd_history")
    op.execute("DROP INDEX IF EXISTS ix_applications_user_jd_applied")
    op.drop_index('ix_applications_kind', table_name='applications')
    op.drop_column('applications', 'kind')
