"""
Test that trial slot counter properly prevents users from claiming trials when exhausted.

Critical security test: ensures the trial_total_slots setting properly gates access
and prevents users from claiming trials once the counter reaches 0.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from main import app
from restailor.models import User, CreditLedger
from restailor.security import create_access_token
from restailor.db import SessionLocal
from config_loader import load_config


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def override_trial_slots(tmp_path):
    """Override config to set trial_total_slots to a small number for testing."""
    config_path = tmp_path / "app.toml"
    config_content = """
[credits.signup_grant]
enable_signup_grant = true
signup_grant_cents = 100
trial_total_slots = 2
grant_window_ip_days = 1
grant_window_email_days = 7
grant_window_fingerprint_days = 30

[credits.trial]
require_2fa = false
cooldown_days = 365
"""
    config_path.write_text(config_content)
    
    # Load and set the config
    original_config = app.state.config if hasattr(app.state, 'config') else None
    app.state.config = load_config(str(config_path))
    
    yield
    
    # Restore original config
    if original_config:
        app.state.config = original_config
    elif hasattr(app.state, 'config'):
        delattr(app.state, 'config')


@pytest.mark.critical
@pytest.mark.security
def test_trial_slots_block_when_exhausted(client: TestClient, db: Session, override_trial_slots):
    """
    Test that once trial slots are exhausted (counter reaches 0), 
    new users cannot claim trials.
    
    This test:
    1. Creates 2 users and has them claim trials (total_slots = 2)
    2. Verifies both claims succeed
    3. Creates a 3rd user and attempts to claim trial
    4. Verifies the 3rd user is blocked with 'trials_exhausted' error
    5. Checks trial-eligibility endpoint also returns trials_exhausted
    """
    # Helper to create and verify a user (2FA not required due to config)
    def create_verified_user_with_2fa(username: str) -> tuple[User, str]:
        # Create user
        user = User(username=username, hashed_password="dummy")
        user.is_verified = True
        user.is_email_verified = True
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Generate auth token
        token = create_access_token({"sub": str(user.id)})
        return user, token
    
    # User 1: Claim trial (should succeed)
    user1, token1 = create_verified_user_with_2fa("user1@test.com")
    headers1 = {"Authorization": f"Bearer {token1}"}
    
    resp1 = client.post("/credits/claim-trial", headers=headers1)
    assert resp1.status_code == 200, f"User 1 trial claim failed: {resp1.text}"
    data1 = resp1.json()
    assert data1.get("success") is True
    
    # Verify user1 has trial credit in ledger
    ledger1 = db.query(CreditLedger).filter(
        CreditLedger.user_id == user1.id,
        CreditLedger.note == "signup_grant"
    ).first()
    assert ledger1 is not None, "User 1 trial not found in credit_ledger"
    assert ledger1.amount_cents == 100
    
    # User 2: Claim trial (should succeed - exactly at limit)
    user2, token2 = create_verified_user_with_2fa("user2@test.com")
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    resp2 = client.post("/credits/claim-trial", headers=headers2)
    assert resp2.status_code == 200, f"User 2 trial claim failed: {resp2.text}"
    data2 = resp2.json()
    assert data2.get("success") is True
    
    # Verify user2 has trial credit in ledger
    ledger2 = db.query(CreditLedger).filter(
        CreditLedger.user_id == user2.id,
        CreditLedger.note == "signup_grant"
    ).first()
    assert ledger2 is not None, "User 2 trial not found in credit_ledger"
    assert ledger2.amount_cents == 100
    
    # Verify total claimed is 2
    total_claimed = db.query(CreditLedger).filter(
        CreditLedger.note == "signup_grant"
    ).count()
    assert total_claimed == 2, f"Expected 2 trials claimed, got {total_claimed}"
    
    # User 3: Attempt to claim trial (should FAIL - slots exhausted)
    user3, token3 = create_verified_user_with_2fa("user3@test.com")
    headers3 = {"Authorization": f"Bearer {token3}"}
    
    resp3 = client.post("/credits/claim-trial", headers=headers3)
    assert resp3.status_code == 400, f"User 3 should be blocked but got status {resp3.status_code}"
    data3 = resp3.json()
    assert data3.get("detail") == "trials_exhausted", \
        f"Expected 'trials_exhausted' error, got: {data3.get('detail')}"
    
    # Verify user3 has NO trial credit in ledger
    ledger3 = db.query(CreditLedger).filter(
        CreditLedger.user_id == user3.id,
        CreditLedger.note == "signup_grant"
    ).first()
    assert ledger3 is None, "User 3 should not have trial credit but found one in ledger"
    
    # Verify total claimed is still 2 (unchanged)
    total_claimed_after = db.query(CreditLedger).filter(
        CreditLedger.note == "signup_grant"
    ).count()
    assert total_claimed_after == 2, \
        f"Expected 2 trials claimed after block, got {total_claimed_after}"
    
    # Check trial-eligibility endpoint also reflects exhaustion
    eligibility_resp = client.get("/credits/trial-eligibility", headers=headers3)
    assert eligibility_resp.status_code == 200
    eligibility_data = eligibility_resp.json()
    assert eligibility_data.get("eligible") is False, \
        "User 3 should not be eligible for trial"
    assert eligibility_data.get("reason") == "trials_exhausted", \
        f"Expected reason 'trials_exhausted', got: {eligibility_data.get('reason')}"


@pytest.mark.critical
@pytest.mark.security
def test_trial_availability_endpoint_reflects_exhaustion(client: TestClient, db: Session, override_trial_slots):
    """
    Test that the public /public/trial-availability endpoint correctly
    shows remaining trials counting down to 0.
    """
    # Check initial availability (should be 2/2)
    resp_initial = client.get("/public/trial-availability")
    assert resp_initial.status_code == 200
    data_initial = resp_initial.json()
    assert data_initial.get("total") == 2
    assert data_initial.get("available") == 2
    
    # Create user and claim first trial
    def create_verified_user_with_2fa(username: str) -> tuple[User, str]:
        user = User(username=username, hashed_password="dummy")
        user.is_verified = True
        user.is_email_verified = True
        db.add(user)
        db.commit()
        db.refresh(user)
        
        token = create_access_token({"sub": str(user.id)})
        return user, token
    
    user1, token1 = create_verified_user_with_2fa("avail1@test.com")
    headers1 = {"Authorization": f"Bearer {token1}"}
    
    resp1 = client.post("/credits/claim-trial", headers=headers1)
    assert resp1.status_code == 200
    
    # Check availability after first claim (should be 1/2)
    resp_after1 = client.get("/public/trial-availability")
    assert resp_after1.status_code == 200
    data_after1 = resp_after1.json()
    assert data_after1.get("total") == 2
    assert data_after1.get("available") == 1, \
        f"Expected 1 available after first claim, got {data_after1.get('available')}"
    
    # Create user and claim second trial
    user2, token2 = create_verified_user_with_2fa("avail2@test.com")
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    resp2 = client.post("/credits/claim-trial", headers=headers2)
    assert resp2.status_code == 200
    
    # Check availability after second claim (should be 0/2)
    resp_after2 = client.get("/public/trial-availability")
    assert resp_after2.status_code == 200
    data_after2 = resp_after2.json()
    assert data_after2.get("total") == 2
    assert data_after2.get("available") == 0, \
        f"Expected 0 available after second claim, got {data_after2.get('available')}"
    
    # Attempt third claim - should fail
    user3, token3 = create_verified_user_with_2fa("avail3@test.com")
    headers3 = {"Authorization": f"Bearer {token3}"}
    
    resp3 = client.post("/credits/claim-trial", headers=headers3)
    assert resp3.status_code == 400
    assert resp3.json().get("detail") == "trials_exhausted"
    
    # Availability should still be 0/2 (unchanged)
    resp_after3 = client.get("/public/trial-availability")
    assert resp_after3.status_code == 200
    data_after3 = resp_after3.json()
    assert data_after3.get("total") == 2
    assert data_after3.get("available") == 0, \
        f"Expected 0 available after blocked claim, got {data_after3.get('available')}"


@pytest.mark.critical
@pytest.mark.security
def test_trial_slots_zero_blocks_all_users(client: TestClient, db: Session, tmp_path):
    """
    Test that when trial_total_slots is set to 0, no users can claim trials.
    """
    # Override config to set trial_total_slots to 0
    config_path = tmp_path / "app.toml"
    config_content = """
[credits.signup_grant]
enable_signup_grant = true
signup_grant_cents = 100
trial_total_slots = 0
grant_window_ip_days = 1
grant_window_email_days = 7
grant_window_fingerprint_days = 30

[credits.trial]
require_2fa = false
cooldown_days = 365
"""
    config_path.write_text(config_content)
    app.state.config = load_config(str(config_path))
    
    # Create verified user (2FA not required due to config)
    user = User(username="zero@test.com", hashed_password="dummy")
    user.is_verified = True
    user.is_email_verified = True
    db.add(user)
    db.commit()
    db.refresh(user)
    
    token = create_access_token({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    
    # Check availability shows 0/0
    avail_resp = client.get("/public/trial-availability")
    assert avail_resp.status_code == 200
    avail_data = avail_resp.json()
    assert avail_data.get("total") == 0
    assert avail_data.get("available") == 0
    
    # Attempt to claim trial - should fail immediately
    claim_resp = client.post("/credits/claim-trial", headers=headers)
    assert claim_resp.status_code == 400
    claim_data = claim_resp.json()
    assert claim_data.get("detail") == "trials_exhausted"
    
    # Verify no trial was granted in ledger
    ledger = db.query(CreditLedger).filter(
        CreditLedger.user_id == user.id,
        CreditLedger.note == "signup_grant"
    ).first()
    assert ledger is None, "No trial should be granted when total_slots is 0"
    
    # Check eligibility endpoint
    eligibility_resp = client.get("/credits/trial-eligibility", headers=headers)
    assert eligibility_resp.status_code == 200
    eligibility_data = eligibility_resp.json()
    assert eligibility_data.get("eligible") is False
    assert eligibility_data.get("reason") == "trials_exhausted"
