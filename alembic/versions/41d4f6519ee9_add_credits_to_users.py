"""add credits to users

Revision ID: 41d4f6519ee9
Revises: 2200ed25abb9
Create Date: 2025-08-24 18:14:23.404601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '41d4f6519ee9'
down_revision: Union[str, Sequence[str], None] = '2200ed25abb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Only add the credits column to users
    op.add_column('users', sa.Column('credits', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    # Only drop the credits column
    op.drop_column('users', 'credits')
