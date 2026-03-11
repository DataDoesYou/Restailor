"""add email_logs table

Revision ID: 20250826_1600_add_email_logs
Revises: 20250826_1200_pricing_and_billing
Create Date: 2025-08-26 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20250826_1600_add_email_logs'
down_revision = '20250826_1200_pricing_billing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'email_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('recipient', sa.Text(), nullable=False),
        sa.Column('subject', sa.Text(), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='other'),
        sa.Column('source', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='sent'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('client_id', sa.String(length=64), nullable=True),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_email_logs_user_id_users'), ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_email_logs_created_desc'), 'email_logs', [sa.text('created_at DESC')], unique=False)
    op.create_index(op.f('ix_email_logs_recipient'), 'email_logs', ['recipient'], unique=False)
    op.create_index(op.f('ix_email_logs_kind'), 'email_logs', ['kind'], unique=False)
    op.create_index(op.f('ix_email_logs_status'), 'email_logs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_email_logs_status'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_kind'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_recipient'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_created_desc'), table_name='email_logs')
    op.drop_table('email_logs')
