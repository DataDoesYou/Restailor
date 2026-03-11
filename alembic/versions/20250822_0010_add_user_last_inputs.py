"""add last inputs to users

Revision ID: 20250822_0010
Revises: 20250815_0100_add_job_access_token
Create Date: 2025-08-22 00:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20250822_0010'
down_revision: Union[str, None] = '20250821_0110'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('last_resume_enc', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('last_jd_enc', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('last_jd_enc')
        batch_op.drop_column('last_resume_enc')
