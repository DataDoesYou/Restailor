#!/usr/bin/env python3
"""
Regenerate analytics_job_snapshot_state table from applications table.

This script ensures analytics dashboard shows consistent data with the history page
by regenerating snapshots using the single source of truth (applications table).
"""
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from restailor.db import SessionLocal
from services.analytics_job_snapshot import ensure_snapshot_state
import sqlalchemy as sa
from restailor.models import AnalyticsJobSnapshotState, User


def get_snapshot_counts(session, user_id: int) -> dict:
    """Get snapshot counts for validation."""
    result = session.execute(
        sa.text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN is_applied AND is_active THEN 1 ELSE 0 END) as applied,
                SUM(CASE WHEN is_interviewing AND is_active THEN 1 ELSE 0 END) as interviewing,
                SUM(CASE WHEN is_offer AND is_active THEN 1 ELSE 0 END) as offer,
                SUM(CASE WHEN is_hired AND is_active THEN 1 ELSE 0 END) as hired
            FROM analytics_job_snapshot_state
            WHERE user_id = :user_id
        """),
        {"user_id": user_id}
    ).first()
    
    return {
        "total": result[0] or 0,
        "active": result[1] or 0,
        "applied": result[2] or 0,
        "interviewing": result[3] or 0,
        "offer": result[4] or 0,
        "hired": result[5] or 0,
    }


def regenerate_all_snapshots(session):
    """Regenerate snapshots for all users."""
    logger.info("=" * 80)
    logger.info("REGENERATE ANALYTICS SNAPSHOTS")
    logger.info("=" * 80)
    logger.info("")
    
    # Get all users
    users = session.query(User).all()
    logger.info(f"Found {len(users)} users")
    logger.info("")
    
    total_before = 0
    total_after = 0
    
    for user in users:
        user_id = user.id
        user_email = getattr(user, 'email', None) or getattr(user, 'username', f"user_{user_id}")
        logger.info(f"Processing user {user_id} ({user_email})...")
        
        # Get before counts
        before = get_snapshot_counts(session, user_id)
        total_before += before["active"]
        
        logger.info(f"  Before: {before['total']} total, {before['active']} active")
        logger.info(f"    Applied: {before['applied']}, Interviewing: {before['interviewing']}, "
                   f"Offer: {before['offer']}, Hired: {before['hired']}")
        
        # Delete existing snapshots
        deleted = session.query(AnalyticsJobSnapshotState).filter(
            AnalyticsJobSnapshotState.user_id == user_id
        ).delete(synchronize_session=False)
        logger.info(f"  Deleted {deleted} existing snapshots")
        
        # Regenerate
        try:
            ensure_snapshot_state(session, user_id, force=True, commit=True)
            
            # Get after counts
            after = get_snapshot_counts(session, user_id)
            total_after += after["active"]
            
            logger.info(f"  After: {after['total']} total, {after['active']} active")
            logger.info(f"    Applied: {after['applied']}, Interviewing: {after['interviewing']}, "
                       f"Offer: {after['offer']}, Hired: {after['hired']}")
            
            # Show changes
            changes = []
            for key in ["applied", "interviewing", "offer", "hired"]:
                delta = after[key] - before[key]
                if delta != 0:
                    changes.append(f"{key.capitalize()}: {before[key]} → {after[key]} (Δ {delta:+d})")
            
            if changes:
                logger.info("  CHANGES:")
                for change in changes:
                    logger.info(f"    {change}")
            else:
                logger.info("  No changes")
                
        except Exception as ex:
            session.rollback()
            logger.error(f"  Failed to regenerate for user {user_id}: {ex}", exc_info=ex)
            continue
        
        logger.info("")
    
    logger.info("=" * 80)
    logger.info("REGENERATION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total active snapshots: {total_before} → {total_after}")
    logger.info("")


def main():
    """Main entry point."""
    session = SessionLocal()
    try:
        regenerate_all_snapshots(session)
        logger.info("✓ Analytics snapshots regenerated successfully")
        return 0
    except Exception as ex:
        logger.error(f"Regeneration failed: {ex}", exc_info=ex)
        session.rollback()
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
