"""merge user_preferences and applications_job_hash heads

Revision ID: 723e77199c93
Revises: 20251008_applications_job_hash, 20251014_2102_user_prefs
Create Date: 2025-10-14 21:03:38.638496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '723e77199c93'
down_revision: Union[str, Sequence[str], None] = ('20251008_applications_job_hash', '20251014_2102_user_prefs')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
