"""Add encrypted input columns for resume

Revision ID: add_enc_inputs_0002
Revises: bdf5f1265a5c
Create Date: 2025-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_enc_inputs_0002'
down_revision: Union[str, Sequence[str], None] = 'bdf5f1265a5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Ensure pgcrypto is available
	op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
	# Add BYTEA columns for encrypted inputs
	op.add_column('jobs', sa.Column('resume_enc', sa.LargeBinary(), nullable=True))
	op.add_column('jobs', sa.Column('jd_enc', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
	op.drop_column('jobs', 'jd_enc')
	op.drop_column('jobs', 'resume_enc')

