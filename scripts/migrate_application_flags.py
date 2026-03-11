#!/usr/bin/env python3
"""
Migration script: Backfill application flags from jobs.

This one-time migration syncs all application stage flags from their linked jobs,
making the applications table the single source of truth.

Run this BEFORE deploying the refactored code.
"""
from __future__ import annotations

import sys
import logging
from datetime import datetime

from restailor.db import SessionLocal
from restailor.models import Application, User
from services.application_sync import backfill_application_flags_from_jobs
import sqlalchemy as sa

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def verify_before_migration(session):
    """Check current state before migration."""
    logger.info("=" * 80)
    logger.info("PRE-MIGRATION STATE")
    logger.info("=" * 80)
    
    # Count applications by flag
    apps_tbl = Application.__table__
    result = session.execute(
        sa.select(
            sa.func.count().label('total'),
            sa.func.sum(sa.case((apps_tbl.c.is_applied == True, 1), else_=0)).label('applied'),
            sa.func.sum(sa.case((apps_tbl.c.is_interviewing == True, 1), else_=0)).label('interviewing'),
            sa.func.sum(sa.case((apps_tbl.c.is_offer == True, 1), else_=0)).label('offer'),
            sa.func.sum(sa.case((apps_tbl.c.is_hired == True, 1), else_=0)).label('hired'),
        )
    ).one()
    
    logger.info(f"Applications table:")
    logger.info(f"  Total: {result.total}")
    logger.info(f"  Applied: {result.applied}")
    logger.info(f"  Interviewing: {result.interviewing}")
    logger.info(f"  Offer: {result.offer}")
    logger.info(f"  Hired: {result.hired}")
    
    # Count applications with linked jobs
    linked = session.execute(
        sa.select(sa.func.count())
        .select_from(apps_tbl)
        .where(apps_tbl.c.job_id.isnot(None))
    ).scalar()
    
    logger.info(f"  Linked to jobs: {linked}")
    logger.info("")
    
    return result


def verify_after_migration(session, before_state):
    """Verify migration results."""
    logger.info("=" * 80)
    logger.info("POST-MIGRATION STATE")
    logger.info("=" * 80)
    
    apps_tbl = Application.__table__
    result = session.execute(
        sa.select(
            sa.func.count().label('total'),
            sa.func.sum(sa.case((apps_tbl.c.is_applied == True, 1), else_=0)).label('applied'),
            sa.func.sum(sa.case((apps_tbl.c.is_interviewing == True, 1), else_=0)).label('interviewing'),
            sa.func.sum(sa.case((apps_tbl.c.is_offer == True, 1), else_=0)).label('offer'),
            sa.func.sum(sa.case((apps_tbl.c.is_hired == True, 1), else_=0)).label('hired'),
        )
    ).one()
    
    logger.info(f"Applications table:")
    logger.info(f"  Total: {result.total}")
    logger.info(f"  Applied: {result.applied}")
    logger.info(f"  Interviewing: {result.interviewing}")
    logger.info(f"  Offer: {result.offer}")
    logger.info(f"  Hired: {result.hired}")
    logger.info("")
    
    # Show changes
    logger.info("CHANGES:")
    logger.info(f"  Applied: {before_state.applied} → {result.applied} (Δ {result.applied - before_state.applied})")
    logger.info(f"  Interviewing: {before_state.interviewing} → {result.interviewing} (Δ {result.interviewing - before_state.interviewing})")
    logger.info(f"  Offer: {before_state.offer} → {result.offer} (Δ {result.offer - before_state.offer})")
    logger.info(f"  Hired: {before_state.hired} → {result.hired} (Δ {result.hired - before_state.hired})")
    logger.info("")


def run_migration(dry_run: bool = True):
    """
    Run the migration to backfill application flags.
    
    Args:
        dry_run: If True, rollback changes. If False, commit.
    """
    logger.info("=" * 80)
    logger.info(f"MIGRATION: Backfill Application Flags {'(DRY RUN)' if dry_run else '(LIVE)'}")
    logger.info("=" * 80)
    logger.info("")
    
    with SessionLocal() as session:
        try:
            # Check pre-migration state
            before_state = verify_before_migration(session)
            
            # Run backfill
            logger.info("Running backfill...")
            start_time = datetime.now()
            rows_updated = backfill_application_flags_from_jobs(session, commit=False)
            duration = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Backfill completed in {duration:.2f}s")
            logger.info(f"Rows updated: {rows_updated}")
            logger.info("")
            
            # Check post-migration state
            verify_after_migration(session, before_state)
            
            # Commit or rollback
            if dry_run:
                logger.info("DRY RUN: Rolling back changes")
                session.rollback()
                logger.info("✓ Rollback complete - no data was changed")
            else:
                logger.info("LIVE RUN: Committing changes...")
                session.commit()
                logger.info("✓ Migration committed successfully")
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("MIGRATION COMPLETE")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Migration failed: err_type={type(e).__name__} err_msg={str(e)[:200]}")
            session.rollback()
            logger.info("✗ Changes rolled back due to error")
            raise


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Backfill application flags from jobs'
    )
    parser.add_argument(
        '--live',
        action='store_true',
        help='Run in live mode (commits changes). Default is dry-run.'
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Skip confirmation prompt in live mode'
    )
    
    args = parser.parse_args()
    
    if args.live and not args.yes:
        logger.warning("")
        logger.warning("⚠️  WARNING: You are about to run this migration in LIVE mode.")
        logger.warning("⚠️  This will modify the applications table.")
        logger.warning("")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Migration cancelled by user")
            sys.exit(0)
    
    try:
        run_migration(dry_run=not args.live)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
