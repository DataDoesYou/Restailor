"""add email verification fields to users

Revision ID: 2200ed25abb9
Revises: 20250823_0015
Create Date: 2025-08-24 17:56:02.672458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2200ed25abb9'
down_revision: Union[str, Sequence[str], None] = '20250823_0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Only add the requested columns and indexes on users
    op.add_column('users', sa.Column('is_email_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('email_verification_token', sa.String(length=128), nullable=True))
    op.add_column('users', sa.Column('browser_fingerprint', sa.String(length=128), nullable=True))
    op.create_index(op.f('ix_users_browser_fingerprint'), 'users', ['browser_fingerprint'], unique=False)
    op.create_index(op.f('ix_users_email_verification_token'), 'users', ['email_verification_token'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Only revert the users changes
    op.drop_index(op.f('ix_users_email_verification_token'), table_name='users')
    op.drop_index(op.f('ix_users_browser_fingerprint'), table_name='users')
    op.drop_column('users', 'browser_fingerprint')
    op.drop_column('users', 'email_verification_token')
    op.drop_column('users', 'is_email_verified')
