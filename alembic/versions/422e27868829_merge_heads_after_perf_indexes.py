"""merge heads after perf indexes

Revision ID: 422e27868829
Revises: 20250827_2410_users_trial, 20250828_perf_idx
Create Date: 2025-08-28 01:36:14.419337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '422e27868829'
down_revision: Union[str, Sequence[str], None] = ('20250827_2410_users_trial', '20250828_perf_idx')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
