"""
Comprehensive Stripe Integration Tests

Tests the complete Stripe payment flow:
1. Purchase intent creation
2. Webhook signature verification
3. Purchase credit application
4. Refund processing
5. Idempotency
"""
import json
import hmac
import hashlib
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app, _apply_stripe_purchase, _apply_stripe_refund, CONFIG
from restailor.db import SessionLocal
from restailor.models import User, CreditLedger, UserBalance
from restailor import crud, schemas


@pytest.fixture
def db():
    """Create a test database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def configure_stripe():
    """Ensure Stripe is configured for tests."""
    import os
    
    # Store original values
    original_stripe_config = CONFIG.get("stripe", {}).copy()
    
    # Set test configuration
    if "stripe" not in CONFIG:
        CONFIG["stripe"] = {}
    
    CONFIG["stripe"]["enabled"] = True
    CONFIG["stripe"]["webhook_secret"] = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    CONFIG["stripe"]["publishable_key"] = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_123")
    
    yield
    
    # Restore original configuration
    CONFIG["stripe"] = original_stripe_config


@pytest.fixture
def test_user(db: Session):
    """Create a test user for Stripe tests."""
    import secrets
    email = f"stripe_test_{secrets.token_hex(4)}@example.com"
    user = crud.create_user(
        db,
        schemas.UserCreate(
            username=email,
            password="TestPassword123!",
        )
    )
    # Mark as verified and test
    user.is_verified = True
    user.is_test = True
    db.commit()
    db.refresh(user)
    yield user
    # Cleanup
    try:
        db.query(CreditLedger).filter(CreditLedger.user_id == user.id).delete()
        db.query(UserBalance).filter(UserBalance.user_id == user.id).delete()
        db.delete(user)
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture
def auth_headers(test_user):
    """Get auth headers for test user."""
    client = TestClient(app)
    response = client.post(
        "/token",
        data={
            "username": test_user.username,
            "password": "TestPassword123!",
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestPurchaseIntent:
    """Test POST /billing/purchase-intent endpoint."""

    @patch('stripe.checkout.Session.create')
    def test_create_purchase_intent_success(self, mock_stripe_create, auth_headers):
        """Test successful checkout session creation."""
        # Mock Stripe response
        mock_session = Mock()
        mock_session.url = "https://checkout.stripe.com/c/pay/cs_test_123"
        mock_session.id = "cs_test_123"
        mock_stripe_create.return_value = mock_session

        client = TestClient(app)
        response = client.post(
            "/billing/purchase-intent",
            headers=auth_headers,
            json={"amount_usd": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "checkout_url" in data
        assert data["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_123"
        assert data["session_id"] == "cs_test_123"

        # Verify Stripe was called with correct parameters
        mock_stripe_create.assert_called_once()
        call_kwargs = mock_stripe_create.call_args.kwargs
        assert call_kwargs["mode"] == "payment"
        assert call_kwargs["payment_method_types"] == ["card"]
        assert call_kwargs["line_items"][0]["price_data"]["unit_amount"] == 1000  # $10 in cents
        assert "user_id" in call_kwargs["metadata"]
        assert "email" in call_kwargs["metadata"]

    def test_invalid_amount(self, auth_headers):
        """Test rejection of invalid purchase amounts."""
        client = TestClient(app)
        
        # Test disallowed amount
        response = client.post(
            "/billing/purchase-intent",
            headers=auth_headers,
            json={"amount_usd": 7},  # Not in allowed set
        )
        assert response.status_code == 400
        assert "amount_not_allowed" in response.json()["detail"]

    def test_unauthenticated_request(self):
        """Test that unauthenticated requests are rejected."""
        client = TestClient(app)
        response = client.post(
            "/billing/purchase-intent",
            json={"amount_usd": 10},
        )
        assert response.status_code == 401

    @pytest.mark.parametrize("amount", [5, 10, 25, 50, 100])
    def test_all_allowed_amounts(self, auth_headers, amount):
        """Test all allowed purchase amounts."""
        with patch('stripe.checkout.Session.create') as mock_stripe:
            mock_session = Mock()
            mock_session.url = f"https://checkout.stripe.com/c/pay/cs_test_{amount}"
            mock_session.id = f"cs_test_{amount}"
            mock_stripe.return_value = mock_session

            client = TestClient(app)
            response = client.post(
                "/billing/purchase-intent",
                headers=auth_headers,
                json={"amount_usd": amount},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True

            # Verify amount is correctly converted to cents
            call_kwargs = mock_stripe.call_args.kwargs
            assert call_kwargs["line_items"][0]["price_data"]["unit_amount"] == amount * 100

    @patch('stripe.checkout.Session.create')
    def test_stripe_error_handling(self, mock_stripe_create, auth_headers):
        """Test handling of Stripe API errors."""
        # Simulate Stripe API error
        mock_stripe_create.side_effect = Exception("Stripe API Error")

        client = TestClient(app)
        response = client.post(
            "/billing/purchase-intent",
            headers=auth_headers,
            json={"amount_usd": 10},
        )

        assert response.status_code == 500
        assert "checkout_creation_failed" in response.json()["detail"]


class TestWebhookSignatureVerification:
    """Test Stripe webhook signature verification."""

    def create_webhook_signature(self, payload: str, secret: str, timestamp: str | None = None) -> str:
        """Create a valid Stripe webhook signature."""
        if timestamp is None:
            import time
            timestamp = str(int(time.time()))
        
        signed_payload = f"{timestamp}.{payload}"
        signature = hmac.new(
            secret.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"t={timestamp},v1={signature}"

    def test_valid_signature(self, test_user):
        """Test webhook with valid signature."""
        client = TestClient(app)
        
        # Use the actual webhook secret from config
        import os
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
        
        payload = json.dumps({
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "amount_total": 1000,
                    "metadata": {
                        "user_id": str(test_user.id),
                        "email": test_user.username,
                    }
                }
            }
        })
        
        signature = self.create_webhook_signature(payload, secret)
        
        response = client.post(
            "/webhooks/stripe",
            content=payload,
            headers={"Stripe-Signature": signature},
        )
        
        # Should succeed (200) or indicate user mapping issue (202)
        assert response.status_code in [200, 202]

    def test_missing_signature(self):
        """Test webhook without signature header."""
        client = TestClient(app)
        
        payload = json.dumps({
            "type": "checkout.session.completed",
            "data": {"object": {}}
        })
        
        response = client.post(
            "/webhooks/stripe",
            content=payload,
        )
        
        assert response.status_code == 400
        assert "missing_signature" in response.json()["detail"]

    def test_invalid_signature(self, test_user):
        """Test webhook with invalid signature."""
        client = TestClient(app)
        
        payload = json.dumps({
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "amount_total": 1000,
                    "metadata": {"user_id": str(test_user.id)}
                }
            }
        })
        
        # Invalid signature
        response = client.post(
            "/webhooks/stripe",
            content=payload,
            headers={"Stripe-Signature": "t=123,v1=invalid"},
        )
        
        assert response.status_code == 400
        assert "invalid_signature" in response.json()["detail"]


class TestCreditApplication:
    """Test credit application via webhook."""

    def test_purchase_applies_credits(self, test_user):
        """Test that purchase webhook correctly applies credits."""
        with SessionLocal() as db:
            initial_balance = db.get(UserBalance, test_user.id)
            initial_cents = int(initial_balance.balance_cents) if initial_balance else 0

            # Apply purchase
            applied, new_balance = _apply_stripe_purchase(
                db,
                user_id=test_user.id,
                amount_cents=1000,  # $10
                provider_ref="stripe:purchase:cs_test_123"
            )

            assert applied is True
            assert new_balance == initial_cents + 1000

            # Verify ledger entry
            ledger = db.query(CreditLedger).filter(
                CreditLedger.user_id == test_user.id,
                CreditLedger.provider_ref == "stripe:purchase:cs_test_123"
            ).first()

            assert ledger is not None
            assert ledger.type == "purchase"
            assert ledger.delta_cents == 1000
            assert ledger.note == "stripe_purchase"

    def test_idempotent_purchase(self, test_user):
        """Test that duplicate webhooks don't double-credit."""
        with SessionLocal() as db:
            # First application
            applied1, balance1 = _apply_stripe_purchase(
                db,
                user_id=test_user.id,
                amount_cents=1000,
                provider_ref="stripe:purchase:cs_test_duplicate"
            )
            assert applied1 is True

            # Second application with same provider_ref
            applied2, balance2 = _apply_stripe_purchase(
                db,
                user_id=test_user.id,
                amount_cents=1000,
                provider_ref="stripe:purchase:cs_test_duplicate"
            )
            assert applied2 is False  # Should not apply again
            assert balance2 == balance1  # Balance unchanged

            # Verify only one ledger entry
            count = db.query(CreditLedger).filter(
                CreditLedger.provider_ref == "stripe:purchase:cs_test_duplicate"
            ).count()
            assert count == 1

    def test_refund_deducts_credits(self, test_user):
        """Test that refund webhook correctly deducts credits."""
        with SessionLocal() as db:
            # First add some credits
            _apply_stripe_purchase(
                db,
                user_id=test_user.id,
                amount_cents=1000,
                provider_ref="stripe:purchase:cs_test_refund_original"
            )

            balance_before = db.get(UserBalance, test_user.id)
            assert balance_before is not None
            balance_cents = int(balance_before.balance_cents)

            # Apply refund
            applied, new_balance = _apply_stripe_refund(
                db,
                user_id=test_user.id,
                amount_cents=500,  # $5 refund
                provider_ref="stripe:refund:re_test_123"
            )

            assert applied is True
            assert new_balance == balance_cents - 500

            # Verify ledger entry
            ledger = db.query(CreditLedger).filter(
                CreditLedger.user_id == test_user.id,
                CreditLedger.provider_ref == "stripe:refund:re_test_123"
            ).first()

            assert ledger is not None
            assert ledger.type == "refund"
            assert ledger.delta_cents == -500
            assert ledger.note == "stripe_refund"

    def test_multiple_purchases(self, test_user):
        """Test multiple purchases accumulate correctly."""
        with SessionLocal() as db:
            purchases = [
                ("cs_test_1", 500),   # $5
                ("cs_test_2", 1000),  # $10
                ("cs_test_3", 2500),  # $25
            ]

            for ref_id, amount_cents in purchases:
                _apply_stripe_purchase(
                    db,
                    user_id=test_user.id,
                    amount_cents=amount_cents,
                    provider_ref=f"stripe:purchase:{ref_id}"
                )

            final_balance = db.get(UserBalance, test_user.id)
            assert final_balance is not None
            # Total: $5 + $10 + $25 = $40 = 4000 cents
            assert int(final_balance.balance_cents) >= 4000


class TestWebhookEventHandling:
    """Test different Stripe webhook event types."""

    def test_checkout_session_completed(self, test_user):
        """Test handling of checkout.session.completed event."""
        # This is tested implicitly in other tests
        pass

    def test_payment_intent_succeeded(self, test_user):
        """Test handling of payment_intent.succeeded event."""
        client = TestClient(app)
        
        import os
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
        
        payload = json.dumps({
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123",
                    "amount": 1000,
                    "metadata": {
                        "user_id": str(test_user.id),
                    }
                }
            }
        })
        
        timestamp = str(int(__import__('time').time()))
        signed = f"{timestamp}.{payload}"
        signature = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        sig_header = f"t={timestamp},v1={signature}"
        
        response = client.post(
            "/webhooks/stripe",
            content=payload,
            headers={"Stripe-Signature": sig_header},
        )
        
        assert response.status_code in [200, 202]

    def test_unknown_event_type(self):
        """Test that unknown events are gracefully ignored."""
        client = TestClient(app)
        
        import os
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
        
        payload = json.dumps({
            "type": "customer.created",  # Not handled
            "data": {"object": {}}
        })
        
        timestamp = str(int(__import__('time').time()))
        signed = f"{timestamp}.{payload}"
        signature = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        sig_header = f"t={timestamp},v1={signature}"
        
        response = client.post(
            "/webhooks/stripe",
            content=payload,
            headers={"Stripe-Signature": sig_header},
        )
        
        # Should return 200 (acknowledged but not processed)
        assert response.status_code == 200


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_user_not_found_in_webhook(self):
        """Test webhook with non-existent user ID."""
        client = TestClient(app)
        
        import os
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
        
        payload = json.dumps({
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "amount_total": 1000,
                    "metadata": {
                        "user_id": "999999",  # Non-existent
                    }
                }
            }
        })
        
        timestamp = str(int(__import__('time').time()))
        signed = f"{timestamp}.{payload}"
        signature = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        sig_header = f"t={timestamp},v1={signature}"
        
        response = client.post(
            "/webhooks/stripe",
            content=payload,
            headers={"Stripe-Signature": sig_header},
        )
        
        # Should return 202 (accepted but user not found)
        assert response.status_code == 202

    def test_malformed_json_payload(self):
        """Test webhook with malformed JSON."""
        client = TestClient(app)
        
        import os
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
        
        payload = "{invalid json"
        
        timestamp = str(int(__import__('time').time()))
        signed = f"{timestamp}.{payload}"
        signature = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        sig_header = f"t={timestamp},v1={signature}"
        
        response = client.post(
            "/webhooks/stripe",
            content=payload,
            headers={"Stripe-Signature": sig_header},
        )
        
        assert response.status_code == 400
        assert "invalid_json" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
