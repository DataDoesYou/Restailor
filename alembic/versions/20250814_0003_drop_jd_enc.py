"""Drop jd_enc from jobs

Revision ID: drop_jd_enc_0003
Revises: add_enc_inputs_0002
Create Date: 2025-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'drop_jd_enc_0003'
down_revision: Union[str, Sequence[str], None] = 'add_enc_inputs_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('jobs') as batch_op:
        try:
            batch_op.drop_column('jd_enc')
        except Exception:
            pass


def downgrade() -> None:
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.add_column(sa.Column('jd_enc', sa.LargeBinary(), nullable=True))
