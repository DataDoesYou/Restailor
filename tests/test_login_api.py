"""
Pytest test for login and refresh persistence using requests library.
Tests direct API calls without browser automation.
"""
import pytest
import requests
import json
from typing import Dict, Optional


BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "TestPassword123!"


def test_login_and_token_persistence():
    """Test that login stores a bearer token and it can be used for authenticated requests."""
    
    print("\n" + "="*60)
    print("Testing Login + Token Persistence")
    print("="*60)
    
    # Step 1: Login
    print("\n1. Logging in...")
    login_data = {
        "username": TEST_EMAIL,
        "password": TEST_PASSWORD,
    }
    
    login_response = requests.post(
        f"{BASE_URL}/token",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    print(f"   Login response status: {login_response.status_code}")
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    
    login_json = login_response.json()
    print(f"   Response keys: {login_json.keys()}")
    
    # Check if it's pending 2FA
    token_type = login_json.get("token_type", "").lower()
    access_token = login_json.get("access_token")
    
    print(f"   Token type: {token_type}")
    print(f"   Access token present: {bool(access_token)}")
    
    if token_type == "pending_2fa":
        print("\n   ⚠️  2FA required - attempting trusted device auto-complete...")
        
        # Try auto-complete with trusted device
        step2_response = requests.post(
            f"{BASE_URL}/auth/step2",
            json={"remember_device": True},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
        )
        
        print(f"   Step2 response status: {step2_response.status_code}")
        
        if step2_response.status_code == 200:
            step2_json = step2_response.json()
            if step2_json.get("token_type", "").lower() == "bearer":
                access_token = step2_json.get("access_token")
                print(f"   ✓ Trusted device auto-complete succeeded")
            else:
                pytest.skip("2FA required and auto-complete failed. Please disable 2FA for test account.")
        else:
            pytest.skip("2FA required and no trusted device. Please disable 2FA for test account.")
    
    assert access_token, "No access token received"
    print(f"   ✓ Got access token: {access_token[:30]}...")
    
    # Step 2: Verify token works by calling /users/me
    print("\n2. Testing token with /users/me...")
    
    me_response = requests.get(
        f"{BASE_URL}/users/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    print(f"   Status: {me_response.status_code}")
    assert me_response.status_code == 200, f"Token validation failed: {me_response.text}"
    
    user_data = me_response.json()
    print(f"   ✓ Authenticated as: {user_data.get('email')}")
    print(f"   User ID: {user_data.get('id')}")
    
    # Step 3: Simulate refresh by using the same token again
    print("\n3. Simulating page refresh (reusing token)...")
    
    me_response_2 = requests.get(
        f"{BASE_URL}/users/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    print(f"   Status: {me_response_2.status_code}")
    assert me_response_2.status_code == 200, "Token no longer works after 'refresh'"
    
    user_data_2 = me_response_2.json()
    print(f"   ✓ Still authenticated as: {user_data_2.get('email')}")
    
    # Step 4: Test other authenticated endpoints
    print("\n4. Testing other authenticated endpoints...")
    
    # Test balance endpoint
    balance_response = requests.get(
        f"{BASE_URL}/users/me/balance",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(f"   Balance endpoint: {balance_response.status_code}")
    assert balance_response.status_code == 200, "Balance endpoint failed"
    
    # Test pricing endpoint
    pricing_response = requests.get(
        f"{BASE_URL}/pricing/average?trim=0.10",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(f"   Pricing endpoint: {pricing_response.status_code}")
    assert pricing_response.status_code == 200, "Pricing endpoint failed"
    
    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED!")
    print("="*60)
    print("\nConclusion:")
    print("- Login successful")
    print("- Bearer token works for authentication")
    print("- Token persists across multiple requests (simulating refresh)")
    print("- All authenticated endpoints accessible")
    print("\nThe backend authentication is working correctly!")
    print("If frontend still logs out on refresh, the issue is:")
    print("  1. Token not being stored in localStorage")
    print("  2. Token not being read from localStorage on refresh")
    print("  3. Token not being sent in Authorization header")
    print("="*60 + "\n")


def test_token_in_authorization_header():
    """Test that the frontend approach of using Authorization header works."""
    
    print("\n" + "="*60)
    print("Testing Authorization Header Approach")
    print("="*60)
    
    # Login first
    login_data = {
        "username": TEST_EMAIL,
        "password": TEST_PASSWORD,
    }
    
    login_response = requests.post(
        f"{BASE_URL}/token",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    assert login_response.status_code == 200
    login_json = login_response.json()
    access_token = login_json.get("access_token")
    
    # Handle 2FA if needed
    if login_json.get("token_type", "").lower() == "pending_2fa":
        step2_response = requests.post(
            f"{BASE_URL}/auth/step2",
            json={"remember_device": True},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
        )
        if step2_response.status_code == 200:
            access_token = step2_response.json().get("access_token")
    
    print(f"\nTesting various endpoints with Authorization header...")
    
    endpoints = [
        ("/users/me", "GET"),
        ("/users/me/balance", "GET"),
        ("/pricing/average?trim=0.10", "GET"),
    ]
    
    all_passed = True
    for endpoint, method in endpoints:
        response = requests.request(
            method,
            f"{BASE_URL}{endpoint}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        status = "✓" if response.status_code == 200 else "✗"
        print(f"  {status} {method} {endpoint}: {response.status_code}")
        if response.status_code != 200:
            all_passed = False
    
    assert all_passed, "Some endpoints failed with bearer token"
    
    print("\n✅ All endpoints work with Authorization: Bearer <token>")
    print("="*60 + "\n")


if __name__ == "__main__":
    # Run with: pytest -v test_login_api.py
    # Or: python test_login_api.py
    print("\n🧪 Running Login API Tests")
    print("="*60)
    print("Testing backend authentication with bearer tokens")
    print("="*60 + "\n")
    
    try:
        test_login_and_token_persistence()
        test_token_in_authorization_header()
        print("\n🎉 All tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
