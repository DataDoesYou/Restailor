"""
Manual test script to verify sidebar settings are saved to database.

Run this to:
1. Create a test user
2. Simulate PUT request to save sidebar settings
3. Verify row created in user_preferences table
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

def test_sidebar_save():
    print("=" * 60)
    print("Testing Sidebar Database Integration")
    print("=" * 60)
    
    # Step 1: Create or login test user
    print("\n1. Creating/logging in test user...")
    
    # Try to register (will fail if user exists, that's OK)
    try:
        register_resp = requests.post(
            f"{BASE_URL}/register",
            json={
                "username": "sidebar_test_user",
                "email": "sidebar_test@example.com",
                "password": "testpass123"
            }
        )
        if register_resp.status_code in [200, 201]:
            print("   ✓ New user created")
        else:
            print(f"   ℹ User might already exist (status: {register_resp.status_code})")
    except Exception as e:
        print(f"   ℹ Registration error (user might exist): {e}")
    
    # Login to get token
    print("\n2. Getting authentication token...")
    token_resp = requests.post(
        f"{BASE_URL}/token",
        data={
            "username": "sidebar_test_user",
            "password": "testpass123"
        }
    )
    
    if token_resp.status_code != 200:
        print(f"   ✗ Login failed: {token_resp.status_code}")
        print(f"   Response: {token_resp.text}")
        return
    
    token = token_resp.json()["access_token"]
    print(f"   ✓ Got token: {token[:20]}...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Step 2: Get current settings (should be empty)
    print("\n3. Fetching current settings...")
    get_resp = requests.get(f"{BASE_URL}/users/me/model-settings", headers=headers)
    
    if get_resp.status_code != 200:
        print(f"   ✗ GET failed: {get_resp.status_code}")
        print(f"   Response: {get_resp.text}")
        return
    
    current_settings = get_resp.json()["settings"]
    print(f"   ✓ Current settings: {json.dumps(current_settings, indent=2)}")
    
    # Step 3: Save new sidebar settings (simulate user toggling multi-mode)
    print("\n4. Saving sidebar settings (simulating UI toggle)...")
    
    new_settings = {
        "settings": {
            "multi_model_enabled": True,
            "fit_models": ["gpt-5"],
            "tailor_models": ["gpt-5"],
            "judge_models": [],
            "last_single_fit": None,
            "last_single_tailor": None,
            "last_single_judge": None,
            "version": 1
        }
    }
    
    # Add optimistic lock if we have a timestamp
    if current_settings.get("updated_at"):
        new_settings["expectedUpdatedAt"] = current_settings["updated_at"]
    
    put_resp = requests.put(
        f"{BASE_URL}/users/me/model-settings",
        headers=headers,
        json=new_settings
    )
    
    if put_resp.status_code != 200:
        print(f"   ✗ PUT failed: {put_resp.status_code}")
        print(f"   Response: {put_resp.text}")
        return
    
    updated = put_resp.json()["settings"]
    print(f"   ✓ Settings saved!")
    print(f"   Updated at: {updated.get('updated_at')}")
    print(f"   Multi-mode enabled: {updated.get('multi_model_enabled')}")
    print(f"   Fit models: {updated.get('fit_models')}")
    
    # Step 4: Verify persistence
    print("\n5. Verifying settings persisted...")
    verify_resp = requests.get(f"{BASE_URL}/users/me/model-settings", headers=headers)
    
    if verify_resp.status_code != 200:
        print(f"   ✗ Verification GET failed: {verify_resp.status_code}")
        return
    
    verified = verify_resp.json()["settings"]
    
    if verified["multi_model_enabled"] == True and "gpt-5" in verified["fit_models"]:
        print("   ✓ Settings persisted correctly!")
        print(f"   Multi-mode: {verified['multi_model_enabled']}")
        print(f"   Fit models: {verified['fit_models']}")
    else:
        print("   ✗ Settings did not persist correctly")
        print(f"   Got: {json.dumps(verified, indent=2)}")
    
    print("\n" + "=" * 60)
    print("✓ Test complete! Check your database:")
    print("  SELECT * FROM user_preferences WHERE user_id IN")
    print("    (SELECT id FROM users WHERE email = 'sidebar_test@example.com');")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_sidebar_save()
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
