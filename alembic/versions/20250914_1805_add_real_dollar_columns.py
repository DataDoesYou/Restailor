"""add real dollar columns

Revision ID: 20250914_1805
Revises: 20250914_1700_add_real_token_columns
Create Date: 2025-09-14 18:05:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250914_1805"
# Updated to reflect shortened revision id of prior migration (length <=32 constraint)
down_revision = "20250914_1700_rt_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add nullable real cost columns (populated only when provider real token usage applied)
    op.add_column("charges", sa.Column("cost_usd_real", sa.Numeric(12, 6), nullable=True))
    op.add_column("charges", sa.Column("price_to_user_usd_real", sa.Numeric(12, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("charges", "price_to_user_usd_real")
    op.drop_column("charges", "cost_usd_real")
