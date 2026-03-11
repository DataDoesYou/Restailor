"""
Quick Manual Stripe Integration Test

Run this script to manually test the Stripe integration end-to-end.
Requires: Stripe CLI running with `stripe listen --forward-to http://localhost:8101/webhooks/stripe`

Usage:
    python test_stripe_manual.py
"""
import requests
import json
import time

# Configuration
API_BASE = "http://localhost:8101"
FRONTEND_BASE = "http://localhost:3000"

# Test credentials (update these)
TEST_EMAIL = "stripe_manual_test@example.com"
TEST_PASSWORD = "TestPassword123!"


def print_section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def signup_and_login():
    """Sign up and login to get auth token."""
    print_section("1. Authentication")
    
    # Try to signup (might fail if user exists, that's OK)
    print(f"Signing up user: {TEST_EMAIL}...")
    signup_resp = requests.post(
        f"{API_BASE}/signup",
        json={
            "username": TEST_EMAIL,
            "password": TEST_PASSWORD,
        }
    )
    if signup_resp.status_code == 200:
        print("✓ Signup successful")
    else:
        print(f"⚠ Signup status: {signup_resp.status_code} (user may already exist)")
    
    # Login
    print("Logging in...")
    login_resp = requests.post(
        f"{API_BASE}/token",
        data={
            "username": TEST_EMAIL,
            "password": TEST_PASSWORD,
        }
    )
    
    if login_resp.status_code != 200:
        print(f"✗ Login failed: {login_resp.status_code}")
        print(login_resp.text)
        return None
    
    token = login_resp.json()["access_token"]
    print(f"✓ Login successful, token: {token[:20]}...")
    return token


def get_initial_balance(token):
    """Get user's current balance."""
    print_section("2. Initial Balance Check")
    
    resp = requests.get(
        f"{API_BASE}/users/me/balance",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if resp.status_code != 200:
        print(f"✗ Failed to get balance: {resp.status_code}")
        return None
    
    balance = resp.json()
    print(f"Current balance: ${balance['balance_usd']} ({balance['balance_cents']} cents)")
    return balance['balance_cents']


def create_purchase_intent(token, amount_usd):
    """Create a Stripe checkout session."""
    print_section(f"3. Create Purchase Intent (${amount_usd})")
    
    resp = requests.post(
        f"{API_BASE}/billing/purchase-intent",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json={"amount_usd": amount_usd}
    )
    
    if resp.status_code != 200:
        print(f"✗ Failed to create purchase intent: {resp.status_code}")
        print(resp.text)
        return None
    
    data = resp.json()
    print(f"✓ Checkout session created")
    print(f"  Session ID: {data['session_id']}")
    print(f"  Checkout URL: {data['checkout_url']}")
    print(f"\nℹ️  To complete payment:")
    print(f"  1. Open this URL in your browser: {data['checkout_url']}")
    print(f"  2. Use test card: 4242 4242 4242 4242")
    print(f"  3. Expiry: 12/34, CVC: 123, ZIP: 12345")
    print(f"  4. Complete the payment")
    
    return data


def wait_for_webhook():
    """Wait for user to complete payment."""
    print_section("4. Waiting for Payment Completion")
    
    print("⏳ Waiting for you to complete the payment in Stripe Checkout...")
    print("   (This script will wait for 3 minutes)")
    print("   Watch the Stripe CLI terminal for webhook events!")
    
    for i in range(36):  # 3 minutes
        time.sleep(5)
        dots = "." * ((i % 3) + 1)
        print(f"   Waiting{dots:<3}", end="\r")
    
    print("\n✓ Wait period complete")


def verify_balance_increased(token, initial_balance, expected_increase):
    """Check if balance increased by expected amount."""
    print_section("5. Verify Balance Increased")
    
    resp = requests.get(
        f"{API_BASE}/users/me/balance",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if resp.status_code != 200:
        print(f"✗ Failed to get balance: {resp.status_code}")
        return False
    
    balance = resp.json()
    new_balance = balance['balance_cents']
    increase = new_balance - initial_balance
    
    print(f"Initial balance: ${initial_balance / 100:.2f}")
    print(f"Current balance: ${new_balance / 100:.2f}")
    print(f"Increase:        ${increase / 100:.2f}")
    
    if increase >= expected_increase:
        print(f"✓ Balance increased by at least ${expected_increase / 100:.2f} - SUCCESS!")
        return True
    else:
        print(f"⚠ Balance increase ({increase / 100:.2f}) is less than expected ({expected_increase / 100:.2f})")
        print("   This might be OK if:")
        print("   - Payment is still processing")
        print("   - Webhook hasn't been received yet")
        print("   - You canceled the payment")
        return False


def check_credit_ledger(token):
    """Check recent credit ledger entries."""
    print_section("6. Recent Credit Ledger Entries")
    
    # This endpoint might require admin access, so we'll skip if not available
    print("ℹ️  Checking ledger (requires admin access)...")
    # Implementation depends on your admin endpoints


def main():
    print("\n" + "=" * 60)
    print("  Stripe Integration Manual Test")
    print("=" * 60)
    print("\nPrerequisites:")
    print("  ✓ Docker containers running")
    print("  ✓ Stripe CLI running: stripe listen --forward-to http://localhost:8101/webhooks/stripe")
    print("  ✓ Stripe enabled in config/app.toml")
    print()
    
    input("Press Enter to start the test...")
    
    # Step 1: Authenticate
    token = signup_and_login()
    if not token:
        print("\n✗ Test failed: Could not authenticate")
        return
    
    # Step 2: Get initial balance
    initial_balance = get_initial_balance(token)
    if initial_balance is None:
        print("\n✗ Test failed: Could not get initial balance")
        return
    
    # Step 3: Create purchase intent
    amount_usd = 10  # $10 test purchase
    purchase_data = create_purchase_intent(token, amount_usd)
    if not purchase_data:
        print("\n✗ Test failed: Could not create purchase intent")
        return
    
    # Step 4: Manual payment step
    print(f"\n{'=' * 60}")
    print("  🌐 OPEN CHECKOUT PAGE")
    print('=' * 60)
    print(f"\n👉 Open this URL: {purchase_data['checkout_url']}\n")
    input("Press Enter AFTER you've completed the payment...")
    
    # Give webhook a moment to process
    print("\n⏳ Waiting 5 seconds for webhook processing...")
    time.sleep(5)
    
    # Step 5: Verify balance
    success = verify_balance_increased(token, initial_balance, amount_usd * 100)
    
    # Summary
    print_section("Test Summary")
    if success:
        print("✅ Stripe integration test PASSED!")
        print("   - Checkout session created successfully")
        print("   - Payment processed")
        print("   - Webhook received and processed")
        print("   - Balance updated correctly")
    else:
        print("⚠️  Test incomplete or failed")
        print("   Check:")
        print("   - Stripe CLI terminal for webhook events")
        print("   - Docker logs: docker logs restailor-api-1 --follow")
        print("   - Database: SELECT * FROM credit_ledger ORDER BY created_at DESC;")
    
    print(f"\n{'=' * 60}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Test interrupted by user")
    except Exception as e:
        print(f"\n\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
