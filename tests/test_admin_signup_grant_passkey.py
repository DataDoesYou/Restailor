"""
Test that passkey-only admin users can access signup grant settings.

This test verifies the fix for the issue where:
1. Admin has passkey (WebAuthn) 2FA but NO TOTP secret
2. Admin completes passkey step-up authentication  
3. Admin tries to fetch /admin/credits/signup-grant
4. Backend should accept passkey-only admins (not require TOTP secret)
"""
import pytest
from fastapi.testclient import TestClient
from main import app
from restailor.db import SessionLocal
from restailor.models import User
from restailor import webauthn_repo, twofa_repo
from sqlalchemy import text


@pytest.fixture
def passkey_only_admin(monkeypatch):
    """Create an admin user with passkey 2FA but no TOTP secret."""
    monkeypatch.setenv("REQUIRE_ADMIN_2FA", "1")  # Enforce admin 2FA check
    
    db = SessionLocal()
    try:
        # Create admin user (note: username column stores email addresses)
        stmt = text("""
            INSERT INTO users (username, hashed_password, role, is_active, is_verified, is_email_verified,
                             two_factor_enabled)
            VALUES (:username, :pwd, 'admin', true, true, true, true)
            RETURNING id
        """)
        result = db.execute(stmt, {
            "username": "passkey@test.com",
            "pwd": "$2b$12$dummy.hash.for.testing.purposes.only.hashed.password"
        })
        user_id = result.scalar()
        db.commit()
        
        # Register a passkey credential for this user
        webauthn_repo.insert_credential(
            db,
            user_id=user_id,
            credential_id="test-passkey-credential-id-12345",
            public_key=b"dummy_public_key_bytes_for_testing",
            sign_count=0,
            transports=["usb", "nfc"],
            aaguid="00000000-0000-0000-0000-000000000000"
        )
        
        yield user_id
    finally:
        # Cleanup
        try:
            db.execute(text("DELETE FROM webauthn_credentials WHERE user_id = :uid"), {"uid": user_id})
            db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
            db.commit()
        except Exception:
            pass
        db.close()


@pytest.mark.asyncio
async def test_passkey_only_admin_can_fetch_signup_grant(passkey_only_admin):
    """Test that passkey-only admin (no TOTP) can access signup grant settings."""
    client = TestClient(app)
    user_id = passkey_only_admin
    
    # Login as the passkey admin
    # NOTE: This is a simplified test - in reality you'd need to:
    # 1. Complete login flow
    # 2. Complete passkey step-up
    # 3. Then access admin endpoints
    
    # For now, we'll test the underlying auth check directly
    db = SessionLocal()
    try:
        # Verify user has passkey but no TOTP
        state = twofa_repo.get_user_2fa_state(db, user_id)
        assert state is not None
        assert state["two_factor_enabled"] is True
        # Note: get_user_2fa_state doesn't return two_factor_type field
        assert state["totp_secret"] is None or state["totp_secret"] == ""
        
        # Verify user has WebAuthn credentials
        has_creds = webauthn_repo.has_credentials(db, user_id)
        assert has_creds is True
        
        # Verify the admin check passes (this is what was failing before)
        from restailor import auth as auth_dep
        user = db.query(User).filter(User.id == user_id).first()
        
        # This should NOT raise an exception for passkey-only admins (require_admin is async)
        result = await auth_dep.require_admin(user, db)
        assert result is not None
        assert result.id == user_id
        
    finally:
        db.close()


@pytest.mark.asyncio
async def test_admin_without_any_2fa_is_rejected():
    """Test that admin without 2FA is rejected."""
    import os
    os.environ["REQUIRE_ADMIN_2FA"] = "1"
    
    db = SessionLocal()
    user_id = None
    try:
        # Create admin user without 2FA (note: username column stores email addresses)
        stmt = text("""
            INSERT INTO users (username, hashed_password, role, is_active, is_verified, is_email_verified,
                             two_factor_enabled)
            VALUES (:username, :pwd, 'admin', true, true, true, false)
            RETURNING id
        """)
        result = db.execute(stmt, {
            "username": "no2fa@test.com",
            "pwd": "$2b$12$dummy.hash.for.testing.purposes.only.hashed.password"
        })
        user_id = result.scalar()
        db.commit()
        
        user = db.query(User).filter(User.id == user_id).first()
        
        # This should raise an exception (require_admin is async)
        from restailor import auth as auth_dep
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            await auth_dep.require_admin(user, db)
        
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "admin_requires_2fa"
        
    finally:
        try:
            if user_id:
                db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
                db.commit()
        except Exception:
            pass
        db.close()
