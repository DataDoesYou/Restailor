"""add composite indexes for scaling

Revision ID: 20250906_add_job_indexes
Revises: 
Create Date: 2025-09-06
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250906_add_job_indexes'
# Adjusted to follow placeholder for lost revision 20250906_expand_charge_req_types
down_revision = '20250906_expand_charge_req_types'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    existing = set()
    res = conn.execute(sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
    for row in res:
        existing.add(row[0])

    # Composite index for frequent listing/filtering by user and recency
    if 'ix_jobs_user_status_created' not in existing:
        op.create_index('ix_jobs_user_status_created', 'jobs', ['user_id', 'status', sa.text('created_at DESC')])
    # Composite index for client concurrency checks
    if 'ix_jobs_client_status' not in existing:
        op.create_index('ix_jobs_client_status', 'jobs', ['client_id', 'status'])
    # Composite index for job_outputs by job and type recency (may have been added manually earlier)
    if 'ix_job_outputs_job_type_created' not in existing:
        op.create_index('ix_job_outputs_job_type_created', 'job_outputs', ['job_id', 'type', sa.text('created_at DESC')])


def downgrade():
    # Use IF EXISTS semantics via raw SQL to be tolerant if one was manually created/removed.
    conn = op.get_bind()
    for name, table in [
        ('ix_job_outputs_job_type_created', 'job_outputs'),
        ('ix_jobs_client_status', 'jobs'),
        ('ix_jobs_user_status_created', 'jobs'),
    ]:
        conn.execute(sa.text(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='{name}') THEN EXECUTE 'DROP INDEX IF EXISTS {name}'; END IF; END $$;"))
