"""add user.role check constraint

Revision ID: v_27_role_check
Revises: 20250827_2355_merge_heads
Create Date: 2025-08-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'v_27_role_check'
down_revision = '20250827_2355_merge_heads'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add CHECK constraint ensuring role is either 'user' or 'admin'
    # Use a named constraint for easy management
    with op.batch_alter_table('users') as batch_op:
        batch_op.create_check_constraint(
            constraint_name='ck_users_role_valid',
            condition=sa.text("role in ('user','admin')")
        )


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        try:
            batch_op.drop_constraint('ck_users_role_valid', type_='check')
        except Exception:
            pass
