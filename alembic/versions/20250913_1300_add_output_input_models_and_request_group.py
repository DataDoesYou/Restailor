"""add output/input model tracking and request_group_id

Revision ID: 20250913_1300
Revises: 20250826_2105_admin_id_ledger
Create Date: 2025-09-13 13:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250913_1300'
down_revision = '20250826_2105_admin_id_ledger'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Rename charges.model_count -> output_models
    with op.batch_alter_table('charges') as batch_op:
        batch_op.alter_column('model_count', new_column_name='output_models')
        batch_op.add_column(sa.Column('input_models', sa.Integer(), nullable=False, server_default='0'))
    op.execute("ALTER TABLE charges ALTER COLUMN input_models DROP DEFAULT")

    # 2. Add nullable analytics columns to jobs
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.add_column(sa.Column('request_group_id', postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column('output_models', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('input_models', sa.Integer(), nullable=True))
        batch_op.create_index('ix_jobs_request_group_id', ['request_group_id'])


def downgrade():
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.drop_index('ix_jobs_request_group_id')
        batch_op.drop_column('input_models')
        batch_op.drop_column('output_models')
        batch_op.drop_column('request_group_id')

    with op.batch_alter_table('charges') as batch_op:
        batch_op.add_column(sa.Column('model_count', sa.Integer(), nullable=False, server_default='1'))
        batch_op.drop_column('input_models')
        batch_op.alter_column('output_models', new_column_name='model_count')
    op.execute("ALTER TABLE charges ALTER COLUMN model_count DROP DEFAULT")
