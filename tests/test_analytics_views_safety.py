"""
Integration test to verify analytics.mv_applications materialized view safety.

This test ensures:
1. Only safe, non-PII columns are exposed in the analytics schema
2. No encrypted blobs (snapshot_enc) leak into analytics views
3. No PII fields (jd_text_norm) are accessible via analytics schema
4. Column whitelist is enforced (no unexpected columns)
"""
from __future__ import annotations

import uuid
import pytest
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from restailor.db import SessionLocal
from restailor.models import Application, User
from backend.crypto_utils import encrypt_json
from tests.utils import signup_and_mark_test
from fastapi.testclient import TestClient
from main import app


# Whitelist of allowed columns in analytics.mv_applications
# These are the ONLY columns that should be exposed to data warehouse consumers
ALLOWED_COLUMNS = {
    "id",
    "user_id",
    "job_id",
    "company",
    "role",
    "jd_url",
    "jd_snippet",
    "jd_hash",
    "base_hash",
    "applied_key",
    "is_applied",
    "is_interviewing",
    "is_offer",
    "is_hired",
    "created_at",
    "updated_at",
}

# Forbidden patterns in column names (indicate PII or encrypted data)
FORBIDDEN_PATTERNS = [
    "_enc",
    "encrypted",
    "blob",
    "snapshot",
    "jd_text_norm",  # PII: full normalized job description text
    "pgp_",  # pgcrypto functions
    "password",
    "secret",
    "key",
]


def test_analytics_mv_applications_column_safety():
    """
    Verify that analytics.mv_applications exposes only whitelisted, safe columns.
    
    This is a critical security test ensuring:
    - No PII leaks to analytics consumers (snapshot_enc, jd_text_norm excluded)
    - No encrypted data exposed (snapshot_enc is bytea blob)
    - Only approved columns are accessible
    - Column names don't contain forbidden patterns
    """
    with SessionLocal() as session:
        # Ensure we have at least one test row in applications table
        _ensure_test_application_exists(session)
        
        # Refresh the materialized view to include our test data
        session.execute(text("REFRESH MATERIALIZED VIEW analytics.mv_applications"))
        session.commit()
        
        # Query the materialized view and inspect column names
        result = session.execute(text("SELECT * FROM analytics.mv_applications LIMIT 1"))
        
        # Get actual column names from the result
        actual_columns = set(result.keys())
        
        # CRITICAL ASSERTION 1: Verify only whitelisted columns exist
        unexpected_columns = actual_columns - ALLOWED_COLUMNS
        assert not unexpected_columns, (
            f"SECURITY VIOLATION: Unexpected columns found in analytics.mv_applications: {unexpected_columns}. "
            f"These columns are not in the approved whitelist and may contain PII or sensitive data. "
            f"Review alembic/versions/20251016_analytics_schema.py and ensure only safe columns are included."
        )
        
        # CRITICAL ASSERTION 2: Verify all expected columns are present
        missing_columns = ALLOWED_COLUMNS - actual_columns
        assert not missing_columns, (
            f"Analytics schema missing expected columns: {missing_columns}. "
            f"This may break downstream ETL consumers. Update migration or whitelist."
        )
        
        # CRITICAL ASSERTION 3: Verify no forbidden patterns in column names
        for column in actual_columns:
            for pattern in FORBIDDEN_PATTERNS:
                assert pattern not in column.lower(), (
                    f"SECURITY VIOLATION: Column '{column}' contains forbidden pattern '{pattern}'. "
                    f"This may indicate PII or encrypted data leaking into analytics schema. "
                    f"Remove this column from analytics.mv_applications immediately."
                )
        
        # Fetch one row to verify data types and content
        row = result.fetchone()
        if row:
            row_dict = dict(zip(result.keys(), row))
            
            # CRITICAL ASSERTION 4: Verify snapshot_enc is NOT present
            assert "snapshot_enc" not in row_dict, (
                "SECURITY VIOLATION: snapshot_enc (encrypted blob) found in analytics view. "
                "This contains PII and MUST NOT be exposed to data warehouse consumers."
            )
            
            # CRITICAL ASSERTION 5: Verify jd_text_norm is NOT present
            assert "jd_text_norm" not in row_dict, (
                "SECURITY VIOLATION: jd_text_norm (full job description text) found in analytics view. "
                "This is PII and MUST NOT be exposed to data warehouse consumers."
            )
            
            # Informational: Verify expected data types
            assert isinstance(row_dict["id"], uuid.UUID), "id should be UUID"
            assert isinstance(row_dict["user_id"], int), "user_id should be integer"
            assert isinstance(row_dict["is_applied"], bool), "is_applied should be boolean"
            assert isinstance(row_dict["created_at"], datetime), "created_at should be datetime"
            assert isinstance(row_dict["updated_at"], datetime), "updated_at should be datetime"
            
            # Informational: Verify jd_snippet is truncated (not full text)
            if row_dict["jd_snippet"]:
                assert len(row_dict["jd_snippet"]) <= 500, (
                    f"jd_snippet should be truncated to max 500 chars, got {len(row_dict['jd_snippet'])}"
                )


def test_analytics_mv_applications_filters_test_data():
    """
    Verify that analytics.mv_applications filters out test data (is_test = false).
    
    Data warehouse consumers should only see production data, not test/dev/e2e rows.
    """
    with SessionLocal() as session:
        # Create test user
        client = TestClient(app)
        email = f"analytics_safety_test+{uuid.uuid4()}@example.com"
        signup_and_mark_test(client, email)
        
        user = session.query(User).filter(User.username == email).first()
        assert user is not None
        
        # Create two applications: one test, one production
        test_jd = "Test Job Description for Safety Verification"
        prod_jd = "Production Job Description for Safety Verification"
        resume = "Test Resume Content"
        
        # Test application (is_test=True)
        test_app = _create_test_application(
            session, 
            user.id, 
            test_jd, 
            resume,
            is_test=True
        )
        
        # Production application (is_test=False)
        prod_app = _create_test_application(
            session,
            user.id,
            prod_jd,
            resume,
            is_test=False
        )
        
        session.commit()
        
        # Refresh materialized view
        session.execute(text("REFRESH MATERIALIZED VIEW analytics.mv_applications"))
        session.commit()
        
        # Query the view for our test user's applications
        result = session.execute(
            text(
                "SELECT id, jd_snippet FROM analytics.mv_applications "
                "WHERE user_id = :user_id"
            ),
            {"user_id": user.id}
        )
        rows = result.fetchall()
        
        # Should only contain the production application (is_test=False)
        app_ids = {row[0] for row in rows}
        
        assert prod_app.id in app_ids, (
            "Production application (is_test=False) should be in analytics.mv_applications"
        )
        assert test_app.id not in app_ids, (
            "Test application (is_test=True) should be FILTERED OUT of analytics.mv_applications. "
            "Data warehouse consumers must not see test data."
        )


def test_analytics_schema_access_control():
    """
    Verify that analytics schema exists and is isolated from public schema.
    
    This test ensures:
    - analytics schema exists
    - analytics.mv_applications exists
    - It's a materialized view (not a regular table)
    """
    with SessionLocal() as session:
        # Verify analytics schema exists
        result = session.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name = 'analytics'"
            )
        )
        assert result.fetchone() is not None, (
            "analytics schema does not exist. Run migration: "
            "alembic upgrade head"
        )
        
        # Verify mv_applications exists as a materialized view
        result = session.execute(
            text(
                "SELECT matviewname FROM pg_matviews "
                "WHERE schemaname = 'analytics' AND matviewname = 'mv_applications'"
            )
        )
        assert result.fetchone() is not None, (
            "analytics.mv_applications materialized view does not exist. Run migration: "
            "alembic upgrade head"
        )
        
        # Verify it has a unique index (required for REFRESH CONCURRENTLY)
        result = session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'analytics' "
                "AND tablename = 'mv_applications' "
                "AND indexname = 'ix_mv_applications_id'"
            )
        )
        assert result.fetchone() is not None, (
            "analytics.mv_applications missing unique index on id column. "
            "REFRESH CONCURRENTLY will fail without it."
        )


def test_analytics_no_write_access():
    """
    Verify that materialized view is read-only (cannot INSERT/UPDATE/DELETE).
    
    This prevents accidental data corruption in analytics layer.
    """
    with SessionLocal() as session:
        # Attempt to insert into materialized view (should fail)
        try:
            session.execute(
                text(
                    "INSERT INTO analytics.mv_applications (id, user_id, jd_hash, base_hash, applied_key, "
                    "is_applied, is_interviewing, is_offer, is_hired, created_at, updated_at) "
                    "VALUES (:id, 1, 'hash', 'hash', 'key', false, false, false, false, now(), now())"
                ),
                {"id": uuid.uuid4()}
            )
            session.commit()
            pytest.fail(
                "SECURITY VIOLATION: Successfully inserted into analytics.mv_applications. "
                "Materialized views should be read-only!"
            )
        except Exception as e:
            # Expected: Cannot insert into materialized view
            assert "cannot insert into" in str(e).lower() or "materialized view" in str(e).lower(), (
                f"Expected 'cannot insert into materialized view' error, got: {e}"
            )
            session.rollback()


# --- Test Helper Functions ---

def _ensure_test_application_exists(session: Session) -> Application:
    """
    Ensure at least one test application exists in the database.
    Returns existing or newly created test application.
    """
    # Check if any test application already exists
    existing = session.execute(
        text("SELECT id FROM applications WHERE is_test = true LIMIT 1")
    ).fetchone()
    
    if existing:
        return session.query(Application).filter(Application.id == existing[0]).first()
    
    # Create test user if needed
    email = f"analytics_test_user+{uuid.uuid4()}@example.com"
    client = TestClient(app)
    signup_and_mark_test(client, email)
    
    user = session.query(User).filter(User.username == email).first()
    assert user is not None
    
    # Create test application
    return _create_test_application(
        session,
        user.id,
        "Test Job Description for Analytics Safety",
        "Test Resume Content",
        is_test=True
    )


def _create_test_application(
    session: Session,
    user_id: int,
    jd_text: str,
    resume_text: str,
    is_test: bool = True,
) -> Application:
    """
    Create a test application with minimal required fields.
    """
    from backend.hash_utils import compute_applied_key
    from restailor.applications_api import _derive_jd_projection, _derive_job_input_hashes
    
    jd_hash, base_hash, applied_key = compute_applied_key(user_id, jd_text, resume_text)
    
    snapshot_payload = {
        "jdInput": jd_text,
        "resumeInput": resume_text,
        "tailored": "Test tailored output",
    }
    
    snapshot_enc = encrypt_json(snapshot_payload, session=session)
    jd_snippet, jd_text_norm = _derive_jd_projection(jd_text, snapshot_payload)
    job_hashes = _derive_job_input_hashes(resume_text, jd_text, snapshot_payload)
    
    app = Application.upsert(
        session,
        user_id=user_id,
        jd_hash=jd_hash,
        base_hash=base_hash,
        snapshot_enc=snapshot_enc,
        company="Test Company Analytics",
        role="Analytics Safety Engineer",
        jd_url="https://example.com/job/test",
        jd_snippet=jd_snippet,
        jd_text_norm=jd_text_norm,
        is_test=is_test,
        is_applied=False,
        job_input_hashes=job_hashes,
    )
    
    session.commit()
    return app
