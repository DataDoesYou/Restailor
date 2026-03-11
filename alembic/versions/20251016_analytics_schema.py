"""add analytics schema and materialized view for safe data warehouse access

Revision ID: 20251016_analytics_schema
Revises: 20251015_0100_test_checkbox_table
Create Date: 2025-10-16 00:00:00.000000

This migration creates:
1. analytics schema for downstream data warehouse consumption
2. analytics.mv_applications materialized view with safe, non-PII columns
3. Indexes on the materialized view for performance
4. Grant SELECT to analytics_reader role (if exists)

The materialized view excludes PII fields (snapshot_enc, jd_text_norm) and filters
out test data (is_test = false).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251016_analytics_schema"
down_revision: Union[str, None] = "20251015_0100_test_checkbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create analytics schema and initial materialized view.
    
    Idempotent: Safe to run multiple times.
    """
    # 1. Create analytics schema (idempotent)
    op.execute("""
        CREATE SCHEMA IF NOT EXISTS analytics;
    """)
    
    # 2. Create materialized view with safe, non-PII columns only
    # Note: Using CREATE OR REPLACE is not supported for materialized views in PostgreSQL
    # So we drop if exists first to make this idempotent
    op.execute("""
        DROP MATERIALIZED VIEW IF EXISTS analytics.mv_applications CASCADE;
    """)
    
    op.execute("""
        CREATE MATERIALIZED VIEW analytics.mv_applications AS
        SELECT
            id,
            user_id,
            job_id,
            company,
            role,
            jd_url,
            jd_snippet,
            jd_hash,
            base_hash,
            applied_key,
            is_applied,
            is_interviewing,
            is_offer,
            is_hired,
            created_at,
            updated_at
        FROM public.applications
        WHERE COALESCE(is_test, false) = false
        WITH DATA;
    """)
    
    # 3. Create indexes on materialized view for performance
    # Note: Indexes are automatically dropped when MV is dropped (CASCADE above)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mv_applications_user_id 
        ON analytics.mv_applications (user_id);
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mv_applications_created_at 
        ON analytics.mv_applications (created_at DESC);
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mv_applications_updated_at 
        ON analytics.mv_applications (updated_at DESC);
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mv_applications_is_applied 
        ON analytics.mv_applications (is_applied) WHERE is_applied = true;
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mv_applications_job_id 
        ON analytics.mv_applications (job_id) WHERE job_id IS NOT NULL;
    """)
    
    # 4. Grant SELECT on analytics schema objects to analytics_reader role (if exists)
    # Use DO block for conditional grant to avoid failures if role doesn't exist
    op.execute("""
        DO $$
        BEGIN
            -- Check if analytics_reader role exists
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analytics_reader') THEN
                -- Grant usage on schema
                GRANT USAGE ON SCHEMA analytics TO analytics_reader;
                
                -- Grant SELECT on the materialized view
                GRANT SELECT ON analytics.mv_applications TO analytics_reader;
                
                -- Grant SELECT on all future tables/views in analytics schema
                ALTER DEFAULT PRIVILEGES IN SCHEMA analytics 
                GRANT SELECT ON TABLES TO analytics_reader;
                
                RAISE NOTICE 'Granted SELECT privileges to analytics_reader role';
            ELSE
                RAISE NOTICE 'analytics_reader role does not exist - skipping grants';
            END IF;
        END $$;
    """)
    
    # 5. Add helpful comment on the materialized view
    op.execute("""
        COMMENT ON MATERIALIZED VIEW analytics.mv_applications IS 
        'Safe, non-PII view of applications for data warehouse consumption. 
        Excludes snapshot_enc and jd_text_norm (PII). 
        Filters out test data (is_test = false).
        
        Refresh schedule: Should be refreshed externally via scheduled job.
        Example: REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.mv_applications;
        
        Note: CONCURRENTLY requires a UNIQUE index. Add if needed:
        CREATE UNIQUE INDEX IF NOT EXISTS ix_mv_applications_id 
        ON analytics.mv_applications (id);';
    """)


def downgrade() -> None:
    """
    Rollback: Drop materialized view and analytics schema.
    
    WARNING: This will delete the analytics schema and all objects within it.
    """
    # Drop materialized view (CASCADE will drop dependent indexes)
    op.execute("""
        DROP MATERIALIZED VIEW IF EXISTS analytics.mv_applications CASCADE;
    """)
    
    # Drop analytics schema
    # Note: Only drops if empty. Use CASCADE to force drop with all objects.
    # Being conservative here - use RESTRICT so it fails if other objects exist
    op.execute("""
        DROP SCHEMA IF EXISTS analytics RESTRICT;
    """)
    
    # Note: We don't revoke grants from analytics_reader because:
    # 1. The schema no longer exists, so grants are automatically removed
    # 2. We don't want to remove the role itself (might be used elsewhere)


# ==============================================================================
# REFRESH INSTRUCTIONS (for external scheduling)
# ==============================================================================
#
# The materialized view should be refreshed periodically to keep data current.
# This can be done via:
#
# 1. Scheduled PostgreSQL job (pg_cron extension):
#    SELECT cron.schedule(
#        'refresh-analytics-mv-applications',
#        '*/15 * * * *',  -- Every 15 minutes
#        $$REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.mv_applications;$$
#    );
#
# 2. Application-level cron job:
#    - Python: use APScheduler, Celery, or similar
#    - Add to your task scheduler/worker pool
#
# 3. Manual refresh (for testing):
#    REFRESH MATERIALIZED VIEW analytics.mv_applications;
#
# 4. Concurrent refresh (recommended for production - no locks):
#    -- First, create a unique index to enable CONCURRENTLY:
#    CREATE UNIQUE INDEX IF NOT EXISTS ix_mv_applications_id 
#    ON analytics.mv_applications (id);
#    
#    -- Then refresh without locking:
#    REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.mv_applications;
#
# ==============================================================================
