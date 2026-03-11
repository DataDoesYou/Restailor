"""Direct webhook test - simulates Stripe sending a webhook"""
import hashlib
import hmac
import json
import os
import time
import requests
import uuid

# Use an explicit env override when validating against a real local config.
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
API_URL = "http://localhost:8000/webhooks/stripe"

# Generate unique IDs for each test
unique_id = str(uuid.uuid4())[:8]
payment_intent_id = f"pi_test_{unique_id}"
checkout_session_id = f"cs_test_{unique_id}"

# Create a minimal checkout.session.completed event
event = {
    "type": "checkout.session.completed",
    "data": {
        "object": {
            "id": checkout_session_id,
            "payment_intent": payment_intent_id,
            "amount_total": 500,  # $5.00 in cents
            "metadata": {
                "user_id": "test-user"
            },
            "customer_email": "test@example.com"
        }
    }
}

# Convert to JSON
payload = json.dumps(event).encode('utf-8')

# Create signature
timestamp = str(int(time.time()))
signed_payload = f"{timestamp}.".encode('utf-8') + payload
signature = hmac.new(
    WEBHOOK_SECRET.encode('utf-8'),
    signed_payload,
    hashlib.sha256
).hexdigest()

# Create Stripe-Signature header
stripe_signature = f"t={timestamp},v1={signature}"

# Send request
headers = {
    "Stripe-Signature": stripe_signature,
    "Content-Type": "application/json"
}

print(f"Sending webhook to {API_URL}")
print(f"Event type: {event['type']}")
print(f"Amount: ${event['data']['object']['amount_total']/100:.2f}")
print(f"User ID: {event['data']['object']['metadata']['user_id']}")
print(f"Payment Intent: {payment_intent_id}")
print(f"Checkout Session: {checkout_session_id}")
print(f"\nStripe-Signature: {stripe_signature[:50]}...")

response = requests.post(API_URL, data=payload, headers=headers)

print(f"\nResponse status: {response.status_code}")
print(f"Response body: {response.text}")
