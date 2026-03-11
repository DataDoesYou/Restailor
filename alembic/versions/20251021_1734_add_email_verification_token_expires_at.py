"""add email_verification_token_expires_at

Revision ID: 20251021_1734
Revises: 20251017_1501_migrate_settings
Create Date: 2025-10-21 17:34:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251021_1734'
down_revision: Union[str, None] = '20251017_1501_migrate_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add email_verification_token_expires_at column to users table
    # Make it nullable to support existing users with tokens that don't have expiry
    # Use inspector to check if column already exists (idempotent)
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'email_verification_token_expires_at' not in columns:
        op.add_column('users', sa.Column('email_verification_token_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Drop the column if rolling back
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'email_verification_token_expires_at' in columns:
        op.drop_column('users', 'email_verification_token_expires_at')
