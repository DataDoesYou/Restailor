"""drop reasoning_tokens_real column

Revision ID: 20250916_0220_drop_reason_real
Revises: 20250916_0210_mult_used
Create Date: 2025-09-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20250916_0220_drop_reason_real"
down_revision = "20250916_0210_mult_used"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("charges") as batch_op:
        conn = op.get_bind()
        insp = sa.inspect(conn)
        cols = [c['name'] for c in insp.get_columns('charges')]
        if 'reasoning_tokens_real' in cols:
            batch_op.drop_column('reasoning_tokens_real')


def downgrade() -> None:
    with op.batch_alter_table("charges") as batch_op:
        conn = op.get_bind()
        insp = sa.inspect(conn)
        cols = [c['name'] for c in insp.get_columns('charges')]
        if 'reasoning_tokens_real' not in cols:
            batch_op.add_column(sa.Column('reasoning_tokens_real', sa.Integer(), nullable=True))
