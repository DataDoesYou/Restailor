"""add multiplier_used to charges

Revision ID: 20250916_0210_mult_used
Revises: 20250916_0200_part_real
Create Date: 2025-09-16 02:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250916_0210_mult_used'
down_revision = '20250916_0200_part_real'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('charges', sa.Column('multiplier_used', sa.Numeric(8,4), nullable=True))
    # Backfill to 5.0000 (current standard multiplier) for existing rows lacking explicit value
    op.execute("UPDATE charges SET multiplier_used = 5.0000 WHERE multiplier_used IS NULL")


def downgrade() -> None:
    op.drop_column('charges', 'multiplier_used')
