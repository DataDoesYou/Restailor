"""
Simplified applications list endpoint - Single Source of Truth version.

This version queries ONLY the applications table for stage data.
No merging with jobs table. Applications table is the source of truth.
"""
from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import unquote
import json
import uuid
from datetime import datetime

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from restailor.models import Application, Job, User
from restailor import auth as auth_dep
from restailor.applications_api import ApplicationListItem, ApplicationListResponse


def list_applications_simple(
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
    request: Request,
    page: int = 1,
    pageSize: int = 50,
    search: str | None = None,
    showAppliedOnly: bool | None = None,
    stages: str | None = None,
    applied: bool | None = None,
    archived: bool | None = None,
    sort: str | None = None,
    dir: str | None = None,
) -> ApplicationListResponse:
    """
    Simplified list endpoint - reads stage flags directly from applications table.
    
    No merging with jobs table for stage data.
    Applications table is the single source of truth.
    """
    if page < 1:
        page = 1
    if pageSize < 1:
        pageSize = 1
    if pageSize > 500:
        pageSize = 500
    
    search_norm = search.strip().lower() if search else None
    
    # Query applications
    q = db.query(Application).filter(Application.user_id == current_user.id)
    
    # Applied filter
    applied_only = bool(showAppliedOnly) or bool(applied)
    if applied_only:
        q = q.filter(Application.is_applied.is_(True))
    
    # Stage filter (direct from applications table - no merging!)
    if isinstance(stages, str) and stages.strip():
        stage_filter_set = {s.strip().lower() for s in stages.split(',') if s.strip()}
        
        conditions = []
        if 'applied' in stage_filter_set:
            conditions.append(Application.is_applied.is_(True))
        if 'interviewing' in stage_filter_set:
            conditions.append(Application.is_interviewing.is_(True))
        if 'offer' in stage_filter_set:
            conditions.append(Application.is_offer.is_(True))
        if 'hired' in stage_filter_set:
            conditions.append(Application.is_hired.is_(True))
        
        if conditions:
            from sqlalchemy import or_
            q = q.filter(or_(*conditions))
    
    # Order by created_at desc (stable)
    rows = q.order_by(Application.created_at.desc()).all()
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[list_applications_simple] Query returned {len(rows)} rows from database")
    
    # Deduplicate by jd_hash (keep latest)
    seen_jd_hashes: set[str] = set()
    records: list[dict[str, Any]] = []
    
    for row in rows:
        jd_hash_val = getattr(row, "jd_hash", None)
        if isinstance(jd_hash_val, str):
            if jd_hash_val in seen_jd_hashes:
                logger.info(f"[list_applications_simple] SKIPPING duplicate jd_hash: {jd_hash_val} (applied_key={row.applied_key})")
                continue
            seen_jd_hashes.add(jd_hash_val)
        
        # Search filter
        if search_norm:
            jd_norm = getattr(row, "jd_text_norm", None)
            if not jd_norm or search_norm not in jd_norm:
                logger.info(f"[list_applications_simple] SKIPPING due to search filter: {row.applied_key}")
                continue
        
        records.append({
            "applied_key": row.applied_key,
            "company": row.company,
            "role": row.role,
            "jd_url": row.jd_url,
            "jd_hash": row.jd_hash,
            "base_hash": row.base_hash,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "jd_snippet": row.jd_snippet,
            "is_applied": row.is_applied,
            # Read flags DIRECTLY from applications table
            "is_interviewing": row.is_interviewing,
            "is_offer": row.is_offer,
            "is_hired": row.is_hired,
            "job_id": row.job_id,
            "job_input_hashes": getattr(row, "job_input_hashes", None) or [],
        })
    
    logger.info(f"[list_applications_simple] After filtering, {len(records)} records remain")
    
    # Get job metadata (for archive status, tokens, etc - NOT for stage flags!)
    job_ids_needed = [rec["job_id"] for rec in records if rec["job_id"]]
    jobs_by_id: dict[str, Job] = {}
    
    if job_ids_needed:
        job_rows = (
            db.query(Job)
            .filter(Job.user_id == current_user.id, Job.id.in_(job_ids_needed))
            .all()
        )
        for job in job_rows:
            jobs_by_id[str(job.id)] = job
    
    # Archive filter (based on job.is_archived)
    if archived is not None:
        filtered_records: list[dict[str, Any]] = []
        for rec in records:
            job_id_val = rec["job_id"]
            job_obj = jobs_by_id.get(str(job_id_val)) if job_id_val else None
            
            if job_obj is None:
                # No job means not archived
                if archived is False:
                    filtered_records.append(rec)
            else:
                # Check job.is_archived
                if bool(getattr(job_obj, "is_archived", False)) == bool(archived):
                    filtered_records.append(rec)
        
        records = filtered_records
    
    # Compute stage label from flags (simple, no merging)
    def _stage_label(is_applied: bool, is_interviewing: bool, is_offer: bool, is_hired: bool) -> str | None:
        """Derive stage label from flags."""
        if is_hired:
            return "hired"
        if is_offer:
            return "offer"
        if is_interviewing:
            return "interviewing"
        if is_applied:
            return "applied"
        return None
    
    # Sorting
    sort_lc = (sort or "").strip().lower()
    dir_lc = (dir or "asc").strip().lower()
    reverse = (dir_lc == "desc")
    
    if sort_lc == "actions":
        # Sort by stage rank
        def _action_rank(rec: dict) -> int:
            is_applied = bool(rec.get("is_applied"))
            is_interviewing = bool(rec.get("is_interviewing"))
            is_offer = bool(rec.get("is_offer"))
            is_hired = bool(rec.get("is_hired"))
            
            # Simple ranking: H > O > I > A
            if is_hired:
                return 4 if is_applied else 7
            if is_offer:
                return 3 if is_applied else 6
            if is_interviewing:
                return 2 if is_applied else 5
            return 1 if is_applied else 0
        
        records.sort(key=_action_rank, reverse=reverse)
    
    elif sort_lc in ("createdat", "updatedat"):
        try:
            records.sort(key=lambda r: datetime.fromisoformat(str(r.get("created_at") or "")), reverse=reverse)
        except Exception:
            records.sort(key=lambda r: str(r.get("created_at") or ""), reverse=reverse)
    
    elif sort_lc == "jdsnippet":
        records.sort(key=lambda r: str(r.get("jd_snippet") or "").lower(), reverse=reverse)
    
    # Pagination
    total = len(records)
    start = (page - 1) * pageSize
    end = start + pageSize
    page_slice = records[start:end]
    
    # Build response items
    items: list[ApplicationListItem] = []
    for rec in page_slice:
        job_id_val = rec["job_id"]
        job_obj = jobs_by_id.get(str(job_id_val)) if job_id_val else None
        
        # Read flags directly from applications (already in rec)
        is_interviewing = bool(rec.get("is_interviewing", False))
        is_offer = bool(rec.get("is_offer", False))
        is_hired = bool(rec.get("is_hired", False))
        
        stage_label = _stage_label(
            bool(rec.get("is_applied", False)),
            is_interviewing,
            is_offer,
            is_hired,
        )
        
        items.append(ApplicationListItem(
            appliedKey=rec["applied_key"],
            company=rec["company"],
            role=rec["role"],
            jdUrl=rec["jd_url"],
            jdHash=rec["jd_hash"],
            baseHash=rec["base_hash"],
            createdAt=rec["created_at"],
            updatedAt=rec["updated_at"],
            jdSnippet=rec["jd_snippet"],
            isApplied=rec["is_applied"],
            jobId=str(job_id_val) if job_id_val else None,
            jobToken=(str(job_obj.access_token) if job_obj else None),
            isArchived=(bool(getattr(job_obj, "is_archived", False)) if job_obj else None),
            isStaged=(bool(getattr(job_obj, "is_staged", False)) if job_obj else None),
            # Stage flags come directly from applications table - NO MERGING!
            interviewing=is_interviewing,
            offer=is_offer,
            hired=is_hired,
            stageLabel=stage_label,
            jobInputHashes=rec.get("job_input_hashes"),
        ))
    
    return ApplicationListResponse(page=page, pageSize=pageSize, total=total, items=items)
