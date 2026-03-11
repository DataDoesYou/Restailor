"""
Application flag synchronization service.

This module ensures the applications table remains the single source of truth
for stage flags (is_interviewing, is_offer, is_hired).

When a job's stage changes, we update all applications with the same jd_hash
to reflect the new state.
"""
from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restailor.models import Application, Job

logger = logging.getLogger(__name__)


def _saturate_flags(
    interviewing: bool,
    offer: bool,
    hired: bool,
) -> tuple[bool, bool, bool]:
    """
    Apply monotonic saturation: hired → offer → interviewing.
    
    If hired=True, then offer and interviewing must also be True.
    If offer=True, then interviewing must also be True.
    """
    if hired:
        offer = True
        interviewing = True
    elif offer:
        interviewing = True
    
    return interviewing, offer, hired


def sync_application_flags_from_job(
    session: Session,
    job: Job,
    *,
    commit: bool = False,
) -> int:
    """
    Sync all applications with the same input_hash to match the job's stage flags.
    
    Args:
        session: Database session
        job: The job whose flags should be propagated to applications
        commit: Whether to commit the transaction
        
    Returns:
        Number of application rows updated
    """
    if not job or not job.input_hash:
        logger.warning("Cannot sync applications: job or input_hash missing")
        return 0
    
    # Get saturated flags from job
    interviewing = bool(getattr(job, "is_interviewing", False))
    offer = bool(getattr(job, "is_offer", False))
    hired = bool(getattr(job, "is_hired", False))
    
    interviewing, offer, hired = _saturate_flags(interviewing, offer, hired)
    
    # Find all applications that link to this job by hash
    # Note: We match by job_input_hashes JSONB array
    stmt = (
        sa.update(Application)
        .where(
            sa.and_(
                Application.user_id == job.user_id,
                Application.job_input_hashes.contains([job.input_hash]),
            )
        )
        .values(
            is_interviewing=interviewing,
            is_offer=offer,
            is_hired=hired,
        )
    )
    
    result = session.execute(stmt)
    count = result.rowcount if hasattr(result, 'rowcount') else 0
    
    if commit:
        session.commit()
    else:
        session.flush()
    
    logger.info(
        "Synced flags to applications",
        extra={
            "job_id": str(job.id),
            "user_id": job.user_id,
            "input_hash": job.input_hash,
            "interviewing": interviewing,
            "offer": offer,
            "hired": hired,
            "rows_updated": count,
        }
    )
    
    return count


def sync_application_flags(
    session: Session,
    user_id: int,
    jd_hash: str | None = None,
    job_input_hash: str | None = None,
    *,
    interviewing: bool = False,
    offer: bool = False,
    hired: bool = False,
    commit: bool = False,
) -> int:
    """
    Directly sync application flags for a specific jd_hash or job_input_hash.
    
    Use this when you don't have a Job object but know the hash and desired flags.
    
    Args:
        session: Database session
        user_id: User ID
        jd_hash: JD hash to match applications (optional)
        job_input_hash: Job input hash to match via job_input_hashes array (optional)
        interviewing: Interviewing flag
        offer: Offer flag
        hired: Hired flag
        commit: Whether to commit the transaction
        
    Returns:
        Number of application rows updated
    """
    if not jd_hash and not job_input_hash:
        logger.warning("Cannot sync: need jd_hash or job_input_hash")
        return 0
    
    # Apply saturation
    interviewing, offer, hired = _saturate_flags(interviewing, offer, hired)
    
    # Build filter conditions
    conditions = [Application.user_id == user_id]
    
    if job_input_hash:
        conditions.append(Application.job_input_hashes.contains([job_input_hash]))
    elif jd_hash:
        conditions.append(Application.jd_hash == jd_hash)
    
    stmt = (
        sa.update(Application)
        .where(sa.and_(*conditions))
        .values(
            is_interviewing=interviewing,
            is_offer=offer,
            is_hired=hired,
        )
    )
    
    result = session.execute(stmt)
    count = result.rowcount if hasattr(result, 'rowcount') else 0
    
    if commit:
        session.commit()
    else:
        session.flush()
    
    logger.info(
        "Synced flags to applications (direct)",
        extra={
            "user_id": user_id,
            "jd_hash": jd_hash,
            "job_input_hash": job_input_hash,
            "interviewing": interviewing,
            "offer": offer,
            "hired": hired,
            "rows_updated": count,
        }
    )
    
    return count


def backfill_application_flags_from_jobs(
    session: Session,
    user_id: int | None = None,
    *,
    commit: bool = False,
) -> int:
    """
    One-time backfill: Copy job flags to all linked applications.
    
    This is used during migration to populate application flags from existing job data.
    
    Args:
        session: Database session
        user_id: Optional user ID to limit backfill (for testing)
        commit: Whether to commit the transaction
        
    Returns:
        Total number of applications updated
    """
    # Step 1: Copy flags from jobs to applications (where job is linked)
    # Use a query + update loop instead of bulk UPDATE with subquery to avoid correlation issues
    
    query = session.query(Application).filter(Application.job_id.isnot(None))
    if user_id:
        query = query.filter(Application.user_id == user_id)
    
    applications = query.all()
    count = 0
    
    for app in applications:
        if not app.job_id:
            continue
        
        # Find the linked job
        job = session.query(Job).filter(
            Job.id == app.job_id,
            Job.deleted_at.is_(None)
        ).first()
        
        if not job:
            continue
        
        # Copy flags from job to application
        changed = False
        if app.is_interviewing != job.is_interviewing:
            app.is_interviewing = job.is_interviewing
            changed = True
        if app.is_offer != job.is_offer:
            app.is_offer = job.is_offer
            changed = True
        if app.is_hired != job.is_hired:
            app.is_hired = job.is_hired
            changed = True
        
        if changed:
            count += 1
    
    # Step 2: Apply saturation (hired → offer → interviewing) to ALL applications
    saturation_query = session.query(Application)
    if user_id:
        saturation_query = saturation_query.filter(Application.user_id == user_id)
    
    all_apps = saturation_query.all()
    
    for app in all_apps:
        changed = False
        
        # hired → must have offer and interviewing
        if app.is_hired:
            if not app.is_offer:
                app.is_offer = True
                changed = True
            if not app.is_interviewing:
                app.is_interviewing = True
                changed = True
        
        # offer → must have interviewing
        elif app.is_offer:
            if not app.is_interviewing:
                app.is_interviewing = True
                changed = True
        
        if changed:
            count += 1
    
    if commit:
        session.commit()
    else:
        session.flush()
    
    logger.info(
        "Backfilled application flags from jobs",
        extra={
            "user_id": user_id,
            "rows_updated": count,
        }
    )
    
    return count
