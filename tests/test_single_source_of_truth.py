"""
Test suite for Single Source of Truth refactor.

Verifies that application flags are correctly synced from jobs
and that the simplified list endpoint returns consistent data.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from restailor.db import SessionLocal
from restailor.models import Application, Job, User
from services.application_sync import (
    sync_application_flags_from_job,
    sync_application_flags,
    backfill_application_flags_from_jobs,
)
from restailor.applications_list_simple import list_applications_simple
from tests.utils import signup_and_mark_test


@pytest.fixture
def test_user() -> User:
    """Create a test user."""
    with SessionLocal() as db:
        user = User(
            id=99999,  # Test user ID
            email=f"test_{uuid.uuid4().hex[:8]}@test.com",
            is_test=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def test_sync_application_flags_from_job(test_user: User):
    """Test syncing application flags from a job."""
    with SessionLocal() as db:
        # Create a job
        job = Job(
            id=uuid.uuid4(),
            user_id=test_user.id,
            input_hash=f"hash_{uuid.uuid4().hex[:8]}",
            is_interviewing=True,
            is_offer=False,
            is_hired=False,
            is_test=True,
        )
        db.add(job)
        db.flush()
        
        # Create applications linked to this job
        app1 = Application(
            id=uuid.uuid4(),
            user_id=test_user.id,
            jd_hash=f"jd_{uuid.uuid4().hex[:8]}",
            base_hash=f"base_{uuid.uuid4().hex[:8]}",
            applied_key=f"key_{uuid.uuid4().hex[:8]}",
            job_id=job.id,
            job_input_hashes=[job.input_hash],
            is_applied=True,
            is_interviewing=False,  # Will be synced
            is_offer=False,
            is_hired=False,
            is_test=True,
        )
        app2 = Application(
            id=uuid.uuid4(),
            user_id=test_user.id,
            jd_hash=f"jd_{uuid.uuid4().hex[:8]}",
            base_hash=f"base_{uuid.uuid4().hex[:8]}",
            applied_key=f"key_{uuid.uuid4().hex[:8]}",
            job_id=job.id,
            job_input_hashes=[job.input_hash],
            is_applied=True,
            is_interviewing=False,  # Will be synced
            is_offer=False,
            is_hired=False,
            is_test=True,
        )
        db.add(app1)
        db.add(app2)
        db.flush()
        
        # Sync flags
        rows_updated = sync_application_flags_from_job(db, job, commit=True)
        
        # Verify
        assert rows_updated == 2
        
        db.refresh(app1)
        db.refresh(app2)
        
        assert app1.is_interviewing is True
        assert app1.is_offer is False
        assert app1.is_hired is False
        
        assert app2.is_interviewing is True
        assert app2.is_offer is False
        assert app2.is_hired is False


def test_sync_application_flags_saturation(test_user: User):
    """Test that flag saturation is applied correctly."""
    with SessionLocal() as db:
        # Create a job with hired=True
        job = Job(
            id=uuid.uuid4(),
            user_id=test_user.id,
            input_hash=f"hash_{uuid.uuid4().hex[:8]}",
            is_interviewing=False,  # Should be saturated to True
            is_offer=False,         # Should be saturated to True
            is_hired=True,
            is_test=True,
        )
        db.add(job)
        db.flush()
        
        # Create application
        app = Application(
            id=uuid.uuid4(),
            user_id=test_user.id,
            jd_hash=f"jd_{uuid.uuid4().hex[:8]}",
            base_hash=f"base_{uuid.uuid4().hex[:8]}",
            applied_key=f"key_{uuid.uuid4().hex[:8]}",
            job_id=job.id,
            job_input_hashes=[job.input_hash],
            is_applied=True,
            is_interviewing=False,
            is_offer=False,
            is_hired=False,
            is_test=True,
        )
        db.add(app)
        db.flush()
        
        # Sync with saturation
        sync_application_flags_from_job(db, job, commit=True)
        
        db.refresh(app)
        
        # All flags should be True due to saturation
        assert app.is_interviewing is True
        assert app.is_offer is True
        assert app.is_hired is True


def test_sync_by_hash(test_user: User):
    """Test syncing flags by job_input_hash."""
    with SessionLocal() as db:
        input_hash = f"hash_{uuid.uuid4().hex[:8]}"
        
        # Create applications with this hash
        app1 = Application(
            id=uuid.uuid4(),
            user_id=test_user.id,
            jd_hash=f"jd_{uuid.uuid4().hex[:8]}",
            base_hash=f"base_{uuid.uuid4().hex[:8]}",
            applied_key=f"key_{uuid.uuid4().hex[:8]}",
            job_input_hashes=[input_hash],
            is_applied=True,
            is_interviewing=False,
            is_offer=False,
            is_hired=False,
            is_test=True,
        )
        db.add(app1)
        db.flush()
        
        # Sync by hash
        rows_updated = sync_application_flags(
            db,
            user_id=test_user.id,
            job_input_hash=input_hash,
            interviewing=False,
            offer=True,  # Will saturate interviewing to True
            hired=False,
            commit=True,
        )
        
        assert rows_updated == 1
        
        db.refresh(app1)
        assert app1.is_interviewing is True  # Saturated
        assert app1.is_offer is True
        assert app1.is_hired is False


def test_simplified_list_endpoint_no_merging(test_user: User):
    """Test that simplified endpoint reads flags directly from applications."""
    with SessionLocal() as db:
        # Create application with specific flags
        app = Application(
            id=uuid.uuid4(),
            user_id=test_user.id,
            jd_hash=f"jd_{uuid.uuid4().hex[:8]}",
            base_hash=f"base_{uuid.uuid4().hex[:8]}",
            applied_key=f"key_{uuid.uuid4().hex[:8]}",
            jd_snippet="Test job posting",
            is_applied=True,
            is_interviewing=True,
            is_offer=False,
            is_hired=False,
            is_test=True,
        )
        db.add(app)
        
        # Create a job with DIFFERENT flags
        job = Job(
            id=uuid.uuid4(),
            user_id=test_user.id,
            input_hash=f"hash_{uuid.uuid4().hex[:8]}",
            is_interviewing=False,  # Different from app
            is_offer=True,          # Different from app
            is_hired=True,          # Different from app
            is_test=True,
        )
        db.add(job)
        
        # Link them
        app.job_id = job.id
        app.job_input_hashes = [job.input_hash]
        db.commit()
        
        # Query using simplified endpoint
        from unittest.mock import Mock
        request = Mock()
        request.headers.get.return_value = None
        
        response = list_applications_simple(
            current_user=test_user,
            db=db,
            request=request,
            page=1,
            pageSize=25,
        )
        
        # Should return application flags, NOT job flags
        assert len(response.items) == 1
        item = response.items[0]
        
        assert item.interviewing is True   # From application
        assert item.offer is False          # From application
        assert item.hired is False          # From application
        
        # Should NOT be merged from job:
        assert item.interviewing != job.is_interviewing
        assert item.offer != job.is_offer
        assert item.hired != job.is_hired


def test_backfill_copies_job_flags_to_applications(test_user: User):
    """Test backfill migration copies job flags to applications."""
    with SessionLocal() as db:
        # Create job with flags
        job = Job(
            id=uuid.uuid4(),
            user_id=test_user.id,
            input_hash=f"hash_{uuid.uuid4().hex[:8]}",
            is_interviewing=True,
            is_offer=True,
            is_hired=False,
            is_test=True,
        )
        db.add(job)
        db.flush()
        
        # Create application linked to job with DIFFERENT flags
        app = Application(
            id=uuid.uuid4(),
            user_id=test_user.id,
            jd_hash=f"jd_{uuid.uuid4().hex[:8]}",
            base_hash=f"base_{uuid.uuid4().hex[:8]}",
            applied_key=f"key_{uuid.uuid4().hex[:8]}",
            job_id=job.id,
            is_applied=True,
            is_interviewing=False,  # Will be updated
            is_offer=False,         # Will be updated
            is_hired=False,
            is_test=True,
        )
        db.add(app)
        db.flush()
        
        # Run backfill
        rows_updated = backfill_application_flags_from_jobs(
            db,
            user_id=test_user.id,
            commit=True,
        )
        
        assert rows_updated > 0
        
        db.refresh(app)
        
        # Should now match job flags
        assert app.is_interviewing is True
        assert app.is_offer is True
        assert app.is_hired is False


def test_applications_match_analytics_after_sync(test_user: User):
    """Test that applications and analytics tables match after sync."""
    from restailor.models import AnalyticsJobSnapshotState
    from services.analytics_job_snapshot import rebuild_snapshot_state
    
    with SessionLocal() as db:
        # Create job
        job = Job(
            id=uuid.uuid4(),
            user_id=test_user.id,
            input_hash=f"hash_{uuid.uuid4().hex[:8]}",
            is_interviewing=False,
            is_offer=False,
            is_hired=True,  # Saturates to all True
            is_test=True,
        )
        db.add(job)
        db.flush()
        
        # Create application
        app = Application(
            id=uuid.uuid4(),
            user_id=test_user.id,
            jd_hash=f"jd_{uuid.uuid4().hex[:8]}",
            base_hash=f"base_{uuid.uuid4().hex[:8]}",
            applied_key=f"key_{uuid.uuid4().hex[:8]}",
            job_id=job.id,
            job_input_hashes=[job.input_hash],
            is_applied=True,
            is_interviewing=False,
            is_offer=False,
            is_hired=False,
            is_test=True,
        )
        db.add(app)
        db.flush()
        
        # Sync application from job
        sync_application_flags_from_job(db, job, commit=True)
        db.refresh(app)
        
        # Rebuild analytics snapshot
        rebuild_snapshot_state(db, test_user.id, include_test_rows=True, commit=True)
        
        # Get analytics snapshot for this application
        snapshot = db.query(AnalyticsJobSnapshotState).filter(
            AnalyticsJobSnapshotState.snapshot_id == app.id
        ).one()
        
        # Applications and analytics should match exactly
        assert app.is_interviewing == snapshot.is_interviewing
        assert app.is_offer == snapshot.is_offer
        assert app.is_hired == snapshot.is_hired
