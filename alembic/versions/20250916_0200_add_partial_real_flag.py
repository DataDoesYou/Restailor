"""add is_partial_real_tokens flag

Revision ID: 20250916_0200_part_real
Revises: 20250916_0110
Create Date: 2025-09-16 02:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250916_0200_part_real'
down_revision = '20250916_0110'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('charges', sa.Column('is_partial_real_tokens', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    # Backfill existing rows where exactly one of the real token columns is non-null
    op.execute(
        """
        UPDATE charges
        SET is_partial_real_tokens = true
        WHERE (
            (prompt_tokens_real IS NOT NULL AND completion_tokens_real IS NULL) OR
            (prompt_tokens_real IS NULL AND completion_tokens_real IS NOT NULL)
        )
        """
    )


def downgrade() -> None:
    op.drop_column('charges', 'is_partial_real_tokens')
