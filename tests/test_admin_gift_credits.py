"""
Test admin gift credits functionality with trial/regular options and email notifications.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import AsyncMock, patch

from main import app
from restailor.models import User, CreditLedger, UserBalance
from tests.utils import (
    create_test_user,
    login_user,
    setup_admin_with_totp,
    get_stepup_token,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_gift_regular_credits_with_email(client: TestClient, db: Session):
    """Test gifting regular credits with email notification"""
    # Create admin and regular user
    admin = setup_admin_with_totp(db)
    target_user = create_test_user(db, email="target@test.com", password="pass123")
    db.commit()
    
    # Login as admin and get stepup token
    admin_token = login_user(client, admin.username, "admin123")
    stepup_token = get_stepup_token(client, admin_token, admin)
    
    # Mock email sending
    with patch("services.admin_credits.send_gift_email_notification", new_callable=AsyncMock) as mock_email:
        mock_email.return_value = True
        
        # Gift regular credits
        response = client.post(
            "/admin/credits/gift",
            json={
                "by_email": "target@test.com",
                "amount_cents": 500,
                "reason": "test gift",
                "is_trial": False,
                "send_email": True,
            },
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Stepup-Token": stepup_token,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["user_id"] == target_user.id
        assert data["new_balance_cents"] == 500
        assert data["email_sent"] is True
        
        # Verify email was called with correct parameters
        mock_email.assert_called_once()
        call_args = mock_email.call_args
        assert call_args[0][0] == "target@test.com"
        assert call_args[0][1] == 500
        assert call_args[0][2] is False  # is_trial
    
    # Verify ledger entry
    ledger = db.query(CreditLedger).filter_by(user_id=target_user.id).first()
    assert ledger is not None
    assert ledger.delta_cents == 500
    assert ledger.type == "grant"
    assert "admin_gift" in ledger.note


def test_gift_trial_credits_with_email(client: TestClient, db: Session):
    """Test gifting trial credits with email notification"""
    # Create admin and regular user
    admin = setup_admin_with_totp(db)
    target_user = create_test_user(db, email="target2@test.com", password="pass123")
    db.commit()
    
    # Login as admin and get stepup token
    admin_token = login_user(client, admin.username, "admin123")
    stepup_token = get_stepup_token(client, admin_token, admin)
    
    # Mock email sending
    with patch("services.admin_credits.send_gift_email_notification", new_callable=AsyncMock) as mock_email:
        mock_email.return_value = True
        
        # Gift trial credits
        response = client.post(
            "/admin/credits/gift",
            json={
                "by_email": "target2@test.com",
                "amount_cents": 1000,
                "reason": "trial promo",
                "is_trial": True,
                "send_email": True,
            },
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Stepup-Token": stepup_token,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["email_sent"] is True
        
        # Verify email was called with is_trial=True
        mock_email.assert_called_once()
        call_args = mock_email.call_args
        assert call_args[0][2] is True  # is_trial
    
    # Verify ledger entry has signup_grant note for trial credits
    ledger = db.query(CreditLedger).filter_by(user_id=target_user.id).first()
    assert ledger is not None
    assert ledger.delta_cents == 1000
    assert ledger.type == "grant"
    assert ledger.note == "signup_grant"  # Trial credits use same note as signup grants


def test_gift_without_email(client: TestClient, db: Session):
    """Test gifting credits without email notification"""
    # Create admin and regular user
    admin = setup_admin_with_totp(db)
    target_user = create_test_user(db, email="target3@test.com", password="pass123")
    db.commit()
    
    # Login as admin and get stepup token
    admin_token = login_user(client, admin.username, "admin123")
    stepup_token = get_stepup_token(client, admin_token, admin)
    
    # Mock email to ensure it's not called
    with patch("services.admin_credits.send_gift_email_notification", new_callable=AsyncMock) as mock_email:
        # Gift credits without email
        response = client.post(
            "/admin/credits/gift",
            json={
                "by_email": "target3@test.com",
                "amount_cents": 750,
                "reason": "no email test",
                "is_trial": False,
                "send_email": False,
            },
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Stepup-Token": stepup_token,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["email_sent"] is None  # No email sent
        
        # Verify email was not called
        mock_email.assert_not_called()


def test_bulk_gift_mixed_trial_and_regular(client: TestClient, db: Session):
    """Test bulk gifting with mixed trial and regular credits"""
    # Create admin and multiple users
    admin = setup_admin_with_totp(db)
    user1 = create_test_user(db, email="bulk1@test.com", password="pass123")
    user2 = create_test_user(db, email="bulk2@test.com", password="pass123")
    user3 = create_test_user(db, email="bulk3@test.com", password="pass123")
    db.commit()
    
    # Login as admin and get stepup token
    admin_token = login_user(client, admin.username, "admin123")
    stepup_token = get_stepup_token(client, admin_token, admin)
    
    # Mock email sending
    with patch("services.admin_credits.send_gift_email_notification", new_callable=AsyncMock) as mock_email:
        mock_email.return_value = True
        
        # Bulk gift with mixed types
        response = client.post(
            "/admin/credits/gift-bulk",
            json={
                "items": [
                    {"email": "bulk1@test.com", "amount_cents": 500, "is_trial": False, "reason": "regular gift"},
                    {"email": "bulk2@test.com", "amount_cents": 1000, "is_trial": True, "reason": "trial gift"},
                    {"email": "bulk3@test.com", "amount_cents": 250, "is_trial": False},
                ],
                "dry_run": False,
                "send_email": True,
                "idempotency_prefix": "test_bulk_mixed",
            },
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Stepup-Token": stepup_token,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["total_rows"] == 3
        assert data["credited_rows"] == 3
        assert data["failed_rows"] == 0
        
        # Verify all details show email sent
        for detail in data["details"]:
            assert detail["status"] == "ok"
            assert detail["email_sent"] is True
        
        # Verify email was called 3 times
        assert mock_email.call_count == 3
    
    # Verify ledger entries
    ledger1 = db.query(CreditLedger).filter_by(user_id=user1.id).first()
    assert ledger1.delta_cents == 500
    assert "admin_gift" in ledger1.note
    
    ledger2 = db.query(CreditLedger).filter_by(user_id=user2.id).first()
    assert ledger2.delta_cents == 1000
    assert ledger2.note == "signup_grant"  # Trial
    
    ledger3 = db.query(CreditLedger).filter_by(user_id=user3.id).first()
    assert ledger3.delta_cents == 250


def test_bulk_gift_dry_run(client: TestClient, db: Session):
    """Test bulk gift dry run doesn't create ledger entries or send emails"""
    # Create admin and user
    admin = setup_admin_with_totp(db)
    user = create_test_user(db, email="dryrun@test.com", password="pass123")
    db.commit()
    
    # Login as admin and get stepup token
    admin_token = login_user(client, admin.username, "admin123")
    stepup_token = get_stepup_token(client, admin_token, admin)
    
    # Mock email to ensure it's not called
    with patch("services.admin_credits.send_gift_email_notification", new_callable=AsyncMock) as mock_email:
        # Dry run bulk gift
        response = client.post(
            "/admin/credits/gift-bulk",
            json={
                "items": [
                    {"email": "dryrun@test.com", "amount_cents": 500, "is_trial": False},
                ],
                "dry_run": True,
                "send_email": True,
            },
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Stepup-Token": stepup_token,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["total_rows"] == 1
        assert data["credited_rows"] == 0  # Dry run doesn't credit
        
        # Verify email was not called
        mock_email.assert_not_called()
    
    # Verify no ledger entry created
    ledger = db.query(CreditLedger).filter_by(user_id=user.id).first()
    assert ledger is None


def test_gift_email_failure_handling(client: TestClient, db: Session):
    """Test that gift succeeds even if email fails"""
    # Create admin and user
    admin = setup_admin_with_totp(db)
    user = create_test_user(db, email="emailfail@test.com", password="pass123")
    db.commit()
    
    # Login as admin and get stepup token
    admin_token = login_user(client, admin.username, "admin123")
    stepup_token = get_stepup_token(client, admin_token, admin)
    
    # Mock email to fail
    with patch("services.admin_credits.send_gift_email_notification", new_callable=AsyncMock) as mock_email:
        mock_email.return_value = False
        
        # Gift with email (but email will fail)
        response = client.post(
            "/admin/credits/gift",
            json={
                "by_email": "emailfail@test.com",
                "amount_cents": 500,
                "is_trial": False,
                "send_email": True,
            },
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Stepup-Token": stepup_token,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["new_balance_cents"] == 500
        assert data["email_sent"] is False  # Email failed but gift succeeded
    
    # Verify ledger entry was still created
    ledger = db.query(CreditLedger).filter_by(user_id=user.id).first()
    assert ledger is not None
    assert ledger.delta_cents == 500


def test_gift_requires_stepup(client: TestClient, db: Session):
    """Test that gift requires step-up authentication"""
    # Create admin and user
    admin = setup_admin_with_totp(db)
    user = create_test_user(db, email="nostepup@test.com", password="pass123")
    db.commit()
    
    # Login as admin (but don't get stepup token)
    admin_token = login_user(client, admin.username, "admin123")
    
    # Try to gift without stepup
    response = client.post(
        "/admin/credits/gift",
        json={
            "by_email": "nostepup@test.com",
            "amount_cents": 500,
            "is_trial": False,
            "send_email": True,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    
    # Should require step-up
    assert response.status_code in [401, 403]
    
    # Verify no ledger entry created
    ledger = db.query(CreditLedger).filter_by(user_id=user.id).first()
    assert ledger is None


def test_gift_idempotency(client: TestClient, db: Session):
    """Test that duplicate gifts with same idempotency key are rejected"""
    # Create admin and user
    admin = setup_admin_with_totp(db)
    user = create_test_user(db, email="idempotent@test.com", password="pass123")
    db.commit()
    
    # Login as admin and get stepup token
    admin_token = login_user(client, admin.username, "admin123")
    stepup_token = get_stepup_token(client, admin_token, admin)
    
    idem_key = "test_idempotency_123"
    
    # First gift
    response1 = client.post(
        "/admin/credits/gift",
        json={
            "by_email": "idempotent@test.com",
            "amount_cents": 500,
            "is_trial": False,
            "send_email": False,
            "idempotency_key": idem_key,
        },
        headers={
            "Authorization": f"Bearer {admin_token}",
            "X-Stepup-Token": stepup_token,
        },
    )
    
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["new_balance_cents"] == 500
    
    # Second gift with same idempotency key
    response2 = client.post(
        "/admin/credits/gift",
        json={
            "by_email": "idempotent@test.com",
            "amount_cents": 500,
            "is_trial": False,
            "send_email": False,
            "idempotency_key": idem_key,
        },
        headers={
            "Authorization": f"Bearer {admin_token}",
            "X-Stepup-Token": stepup_token,
        },
    )
    
    assert response2.status_code == 200
    data2 = response2.json()
    # Balance should still be 500, not 1000
    assert data2["new_balance_cents"] == 500
    
    # Verify only one ledger entry
    ledger_count = db.query(CreditLedger).filter_by(user_id=user.id).count()
    assert ledger_count == 1
