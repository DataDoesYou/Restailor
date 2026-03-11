"""
Test that unchecking Applied cascades to clear I/O/H flags.

This ensures the logical dependency chain is maintained:
Applied → Interviewing → Offer → Hired

If you uncheck Applied, you can't be in any subsequent stage.
"""
import pytest
from sqlalchemy.orm import Session
from restailor.models import Application, User
from restailor.applications_api import jd_delete


@pytest.fixture
def test_user(db_session: Session):
    """Create a test user."""
    user = User(
        id=9999,
        email="test_cascade@example.com",
        is_test=True,
        consent_to_store_outputs=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_application(db_session: Session, test_user: User):
    """Create a test application with all flags set."""
    app = Application(
        user_id=test_user.id,
        jd_hash="test_jd_hash_cascade",
        base_hash="test_base_hash",
        applied_key="test_applied_key_cascade",
        snapshot_enc=b"test_snapshot",
        is_applied=True,
        is_interviewing=True,
        is_offer=True,
        is_hired=True,
        is_test=True,
    )
    db_session.add(app)
    db_session.commit()
    return app


def test_unapply_clears_all_flags(db_session: Session, test_user: User, test_application: Application):
    """Test that unchecking Applied clears I/O/H flags."""
    # Verify initial state
    assert test_application.is_applied is True
    assert test_application.is_interviewing is True
    assert test_application.is_offer is True
    assert test_application.is_hired is True
    
    # Call the delete endpoint (unapply)
    result = jd_delete(
        jdHash=test_application.jd_hash,
        current_user=test_user,
        db=db_session,
        appliedKey=test_application.applied_key,
    )
    
    # Verify response
    assert result["ok"] is True
    assert result["changed"] is True
    
    # Refresh from DB
    db_session.refresh(test_application)
    
    # Verify ALL flags are now False
    assert test_application.is_applied is False, "Applied should be False"
    assert test_application.is_interviewing is False, "Interviewing should cascade to False"
    assert test_application.is_offer is False, "Offer should cascade to False"
    assert test_application.is_hired is False, "Hired should cascade to False"


def test_unapply_with_partial_flags(db_session: Session, test_user: User):
    """Test unapply with only some flags set."""
    app = Application(
        user_id=test_user.id,
        jd_hash="test_jd_hash_partial",
        base_hash="test_base_hash",
        applied_key="test_applied_key_partial",
        snapshot_enc=b"test_snapshot",
        is_applied=True,
        is_interviewing=True,
        is_offer=False,
        is_hired=False,
        is_test=True,
    )
    db_session.add(app)
    db_session.commit()
    
    # Verify initial state
    assert app.is_applied is True
    assert app.is_interviewing is True
    assert app.is_offer is False
    assert app.is_hired is False
    
    # Unapply
    result = jd_delete(
        jdHash=app.jd_hash,
        current_user=test_user,
        db=db_session,
        appliedKey=app.applied_key,
    )
    
    # Refresh from DB
    db_session.refresh(app)
    
    # Verify all flags cleared
    assert app.is_applied is False
    assert app.is_interviewing is False
    assert app.is_offer is False
    assert app.is_hired is False


def test_unapply_idempotent(db_session: Session, test_user: User):
    """Test that unapplying twice doesn't cause errors."""
    app = Application(
        user_id=test_user.id,
        jd_hash="test_jd_hash_idempotent",
        base_hash="test_base_hash",
        applied_key="test_applied_key_idempotent",
        snapshot_enc=b"test_snapshot",
        is_applied=True,
        is_interviewing=True,
        is_offer=True,
        is_hired=True,
        is_test=True,
    )
    db_session.add(app)
    db_session.commit()
    
    # First unapply
    result1 = jd_delete(
        jdHash=app.jd_hash,
        current_user=test_user,
        db=db_session,
        appliedKey=app.applied_key,
    )
    assert result1["ok"] is True
    
    # Second unapply (should succeed but not change anything)
    result2 = jd_delete(
        jdHash=app.jd_hash,
        current_user=test_user,
        db=db_session,
        appliedKey=app.applied_key,
    )
    assert result2["ok"] is True
    
    # Refresh from DB
    db_session.refresh(app)
    
    # All flags should still be False
    assert app.is_applied is False
    assert app.is_interviewing is False
    assert app.is_offer is False
    assert app.is_hired is False
