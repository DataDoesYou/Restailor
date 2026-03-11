"""add provider token columns

Revision ID: 20250915_1900_provider_cols
Revises: 20250914_1805
Create Date: 2025-09-15 19:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection

# revision identifiers, used by Alembic.
revision = '20250915_1900_provider_cols'
down_revision = '20250914_1805'
branch_labels = None
depends_on = None

def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = reflection.Inspector.from_engine(bind)  # type: ignore[arg-type]
    for col in insp.get_columns(table):
        if col.get('name') == column:
            return True
    return False

def upgrade() -> None:
    # Add nullable integer columns if missing
    with op.batch_alter_table('charges') as batch:
        if not _has_column('charges', 'provider_prompt_tokens'):
            batch.add_column(sa.Column('provider_prompt_tokens', sa.Integer(), nullable=True))
        if not _has_column('charges', 'provider_completion_tokens_est'):
            batch.add_column(sa.Column('provider_completion_tokens_est', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Best-effort safe downgrade (only drop if exists)
    with op.batch_alter_table('charges') as batch:
        if _has_column('charges', 'provider_completion_tokens_est'):
            batch.drop_column('provider_completion_tokens_est')
        if _has_column('charges', 'provider_prompt_tokens'):
            batch.drop_column('provider_prompt_tokens')
