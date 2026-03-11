"""add_uq_applications_user_jd_constraint

Revision ID: 226006609a19
Revises: 20251021_1734
Create Date: 2025-10-22 21:17:02.181117

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '226006609a19'
down_revision: Union[str, Sequence[str], None] = '20251021_1734'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get existing constraints on applications table
    constraints = inspector.get_unique_constraints('applications')
    constraint_names = [c['name'] for c in constraints]
    
    # Only create if it doesn't exist
    if 'uq_applications_user_jd' not in constraint_names:
        op.create_unique_constraint(
            'uq_applications_user_jd',
            'applications',
            ['user_id', 'jd_hash']
        )


def downgrade() -> None:
    """Downgrade schema."""
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get existing constraints on applications table
    constraints = inspector.get_unique_constraints('applications')
    constraint_names = [c['name'] for c in constraints]
    
    # Only drop if it exists
    if 'uq_applications_user_jd' in constraint_names:
        op.drop_constraint('uq_applications_user_jd', 'applications', type_='unique')
