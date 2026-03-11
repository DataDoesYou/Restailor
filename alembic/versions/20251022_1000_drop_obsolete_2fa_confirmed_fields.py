"""drop obsolete 2fa confirmed fields

Revision ID: 20251022_1000
Revises: 20251021_1734
Create Date: 2025-10-22 10:00:00.000000

Drops two_factor_confirmed and two_factor_confirmed_at columns from users table.
These fields are no longer needed after refactoring to use two_factor_enabled
as the single source of truth (set only after successful TOTP confirmation).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20251022_1000'
down_revision: Union[str, None] = '226006609a19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop two_factor_confirmed and two_factor_confirmed_at columns."""
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Drop two_factor_confirmed column if it exists
    if 'two_factor_confirmed' in columns:
        op.drop_column('users', 'two_factor_confirmed')
    
    # Drop two_factor_confirmed_at column if it exists
    if 'two_factor_confirmed_at' in columns:
        op.drop_column('users', 'two_factor_confirmed_at')


def downgrade() -> None:
    """Re-add the columns if rolling back (though they won't have meaningful data)."""
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Re-add two_factor_confirmed column
    if 'two_factor_confirmed' not in columns:
        op.add_column('users', sa.Column('two_factor_confirmed', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    
    # Re-add two_factor_confirmed_at column
    if 'two_factor_confirmed_at' not in columns:
        op.add_column('users', sa.Column('two_factor_confirmed_at', sa.DateTime(timezone=True), nullable=True))
