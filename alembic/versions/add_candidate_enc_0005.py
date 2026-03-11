"""Add candidate_enc to jobs

Revision ID: add_candidate_enc_0005
Revises: add_jd_enc_0004
Create Date: 2025-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_candidate_enc_0005'
down_revision: Union[str, Sequence[str], None] = 'add_jd_enc_0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.add_column(sa.Column('candidate_enc', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('jobs') as batch_op:
        try:
            batch_op.drop_column('candidate_enc')
        except Exception:
            pass
