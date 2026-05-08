import uuid

from fastapi.testclient import TestClient

from main import app
from .utils import signup_and_mark_test, login


def test_purchase_intent_is_disabled_for_normal_users():
    client = TestClient(app)
    email = f"stripe_disabled_{uuid.uuid4().hex}@example.com"
    signup_and_mark_test(client, email, "TestPassword123!")
    token = login(client, email, "TestPassword123!")

    response = client.post(
        "/billing/purchase-intent",
        headers={"Authorization": f"Bearer {token}", "Origin": "http://localhost:3000"},
        json={"amount_usd": 10},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "stripe_disabled"


def test_stripe_webhook_is_inert_when_disabled():
    client = TestClient(app)
    response = client.post(
        "/webhooks/stripe",
        content='{"type":"checkout.session.completed","data":{"object":{}}}',
        headers={"Stripe-Signature": "t=123,v1=invalid"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "stripe_disabled"
