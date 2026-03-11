"""add indexes to support incremental ETL on applications table

Revision ID: 20251016_indexes_for_incremental
Revises: 20251016_analytics_schema
Create Date: 2025-10-16 12:00:00.000000

This migration adds indexes to the applications table to support efficient
incremental ETL patterns for data warehouse consumption:

1. ix_applications_updated_at: Standard B-tree index for incremental pulls
   - Enables efficient WHERE updated_at > :watermark queries
   - Critical for time-based incremental loads

2. ix_applications_updated_at_desc: Descending index for latest-first queries
   - Optimizes ORDER BY updated_at DESC patterns
   - Useful for "most recent N changes" queries

3. ix_applications_non_test: Partial index on production data
   - Indexes only rows where is_test = false (production data)
   - Reduces index size and improves query performance
   - Supports analytics queries that filter out test data

All indexes use IF NOT EXISTS guards for idempotent migrations.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251016_indexes_for_incremental"
down_revision: Union[str, None] = "20251016_analytics_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add indexes to support incremental ETL patterns."""
    
    # Index 1: Standard ascending index on updated_at for incremental queries
    # Supports: WHERE updated_at > :watermark ORDER BY updated_at
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_applications_updated_at
        ON applications (updated_at);
        """
    )
    
    # Index 2: Descending index on updated_at for latest-first queries
    # Supports: ORDER BY updated_at DESC LIMIT N (e.g., get latest 1000 changes)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_applications_updated_at_desc
        ON applications (updated_at DESC);
        """
    )
    
    # Index 3: Partial index for non-test data (production rows only)
    # Reduces index size by ~50% in typical dev/test environments
    # Supports: WHERE is_test = false (matches analytics.mv_applications filter)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_applications_non_test
        ON applications (user_id, updated_at)
        WHERE is_test = false;
        """
    )
    
    # Index 4: Partial index on created_at for non-test data
    # Supports time-range queries on production data (e.g., daily summaries)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_applications_non_test_created
        ON applications (created_at DESC)
        WHERE is_test = false;
        """
    )


def downgrade() -> None:
    """Remove incremental ETL indexes."""
    
    # Drop in reverse order of creation
    op.execute("DROP INDEX IF EXISTS ix_applications_non_test_created;")
    op.execute("DROP INDEX IF EXISTS ix_applications_non_test;")
    op.execute("DROP INDEX IF EXISTS ix_applications_updated_at_desc;")
    op.execute("DROP INDEX IF EXISTS ix_applications_updated_at;")
