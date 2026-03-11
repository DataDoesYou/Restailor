"""drop two_factor_type field

Revision ID: 20251022_1100
Revises: 20251022_1000
Create Date: 2025-10-22 11:00:00.000000

Drops two_factor_type column from users table.
This field was redundant because users can have multiple 2FA methods enabled
simultaneously (TOTP and WebAuthn). The available 2FA methods can be determined
by checking totp_secret column and webauthn_credentials table.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20251022_1100'
down_revision: Union[str, None] = '20251022_1000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop two_factor_type column."""
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Drop two_factor_type column if it exists
    if 'two_factor_type' in columns:
        op.drop_column('users', 'two_factor_type')


def downgrade() -> None:
    """Restore two_factor_type column."""
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Re-add two_factor_type column if it doesn't exist
    if 'two_factor_type' not in columns:
        op.add_column('users', sa.Column('two_factor_type', sa.String(length=20), nullable=True))
