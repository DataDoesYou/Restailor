"""Add jd_enc back to jobs

Revision ID: add_jd_enc_0004
Revises: drop_jd_enc_0003
Create Date: 2025-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_jd_enc_0004'
down_revision: Union[str, Sequence[str], None] = 'drop_jd_enc_0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.add_column(sa.Column('jd_enc', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('jobs') as batch_op:
        try:
            batch_op.drop_column('jd_enc')
        except Exception:
            pass
