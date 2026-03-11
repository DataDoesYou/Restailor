"""Add exports_audit table for plaintext export auditing

Revision ID: add_exports_audit_0006
Revises: add_candidate_enc_0005
Create Date: 2025-08-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_exports_audit_0006'
down_revision: Union[str, Sequence[str], None] = 'add_candidate_enc_0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'exports_audit',
        sa.Column('export_id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_name', sa.String(length=256), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('out_dir', sa.Text(), nullable=False),
        sa.Column('tables', sa.Text(), nullable=False),
        sa.Column('totals_json', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
    )
    op.create_index('ix_exports_audit_started_at', 'exports_audit', ['started_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_exports_audit_started_at', table_name='exports_audit')
    op.drop_table('exports_audit')
