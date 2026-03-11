"""Drop token_estimation_error_pct column.

Revision ID: 20250916_0110
Revises: 20250916_0100
Create Date: 2025-09-16 01:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '20250916_0110'
down_revision = '20250916_0100'
branch_labels = None
depends_on = None

def _has_column(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        names = [c['name'] for c in insp.get_columns(table)]
    except Exception:
        return False
    return col in names

def upgrade() -> None:
    try:
        with op.batch_alter_table('charges') as batch:
            if _has_column('charges', 'token_estimation_error_pct'):
                batch.drop_column('token_estimation_error_pct')
    except Exception:
        pass

def downgrade() -> None:
    try:
        with op.batch_alter_table('charges') as batch:
            if not _has_column('charges', 'token_estimation_error_pct'):
                batch.add_column(sa.Column('token_estimation_error_pct', sa.Float(), nullable=True))
    except Exception:
        pass
