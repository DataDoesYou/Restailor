"""Drop provider token diagnostic columns now that real tokens stored.

Revision ID: 20250916_0100
Revises: 20250915_1900
Create Date: 2025-09-16 01:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250916_0100'
down_revision = '20250915_1900_provider_cols'
branch_labels = None
depends_on = None

def _has_column(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        cols = [c['name'] for c in insp.get_columns(table)]
    except Exception:
        return False
    return col in cols

def upgrade() -> None:
    try:
        with op.batch_alter_table('charges') as batch:
            if _has_column('charges', 'provider_prompt_tokens'):
                batch.drop_column('provider_prompt_tokens')
            if _has_column('charges', 'provider_completion_tokens_est'):
                batch.drop_column('provider_completion_tokens_est')
    except Exception:
        # Best-effort; keep migration idempotent
        pass

def downgrade() -> None:
    try:
        with op.batch_alter_table('charges') as batch:
            # Recreate columns (nullable) if reversal needed
            if not _has_column('charges', 'provider_prompt_tokens'):
                batch.add_column(sa.Column('provider_prompt_tokens', sa.Integer(), nullable=True))
            if not _has_column('charges', 'provider_completion_tokens_est'):
                batch.add_column(sa.Column('provider_completion_tokens_est', sa.Integer(), nullable=True))
    except Exception:
        pass
