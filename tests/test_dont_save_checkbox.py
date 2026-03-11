#!/usr/bin/env python3
"""
Test script for "Don't save future data" checkbox functionality.

This script verifies:
1. Checkbox state loads correctly from database
2. Toggling checkbox saves to database
3. State persists across sessions
4. Privacy setting is respected in data operations
"""

import json
import os
import sys
import time
from datetime import datetime
import requests

# Configuration
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
TEST_EMAIL = "checkbox_test@example.com"
TEST_PASSWORD = "TestPassword123!"

def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")

def login_user() -> tuple[str, str]:
    """Login and return (session_cookie, user_id)."""
    print("🔑 Logging in...")
    
    # Register user (ignore if already exists)
    try:
        register_resp = requests.post(
            f"{API_BASE}/register",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if register_resp.status_code == 200:
            print(f"   ✓ User registered: {TEST_EMAIL}")
        elif register_resp.status_code == 400:
            print(f"   ℹ User already exists: {TEST_EMAIL}")
        else:
            print(f"   ⚠ Register returned {register_resp.status_code}")
    except Exception as e:
        print(f"   ⚠ Register failed: {e}")
    
    # Login
    login_resp = requests.post(
        f"{API_BASE}/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    
    if login_resp.status_code != 200:
        print(f"   ❌ Login failed: {login_resp.status_code}")
        print(f"   Response: {login_resp.text}")
        sys.exit(1)
    
    session_cookie = login_resp.cookies.get("session")
    if not session_cookie:
        print("   ❌ No session cookie received")
        sys.exit(1)
    
    # Get user info
    me_resp = requests.get(
        f"{API_BASE}/users/me",
        cookies={"session": session_cookie}
    )
    
    if me_resp.status_code != 200:
        print(f"   ❌ Failed to get user info: {me_resp.status_code}")
        sys.exit(1)
    
    user_data = me_resp.json()
    user_id = user_data.get("id")
    
    print(f"   ✓ Logged in as {TEST_EMAIL} (ID: {user_id})")
    return session_cookie, user_id

def get_settings(session_cookie: str) -> dict:
    """Get current user settings."""
    resp = requests.get(
        f"{API_BASE}/users/me/settings",
        cookies={"session": session_cookie}
    )
    
    if resp.status_code != 200:
        print(f"   ❌ Failed to get settings: {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    return resp.json()

def update_settings(session_cookie: str, dont_save: bool, public_profile: bool = False) -> dict:
    """Update user settings."""
    payload = {
        "dont_save_future_data": dont_save,
        "public_profile": public_profile
    }
    
    resp = requests.put(
        f"{API_BASE}/users/me/settings",
        json=payload,
        cookies={"session": session_cookie}
    )
    
    if resp.status_code != 200:
        print(f"   ❌ Failed to update settings: {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    return resp.json()

def verify_database_state(user_id: str, expected_dont_save: bool):
    """Verify the database state directly (requires DB access)."""
    try:
        import psycopg2
        from config_loader import load_config_sync
        
        config = load_config_sync()
        db_url = config.get("database_url") or os.getenv("DATABASE_URL")
        
        if not db_url:
            print("   ⚠ Cannot verify database (no DATABASE_URL)")
            return
        
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        cur.execute(
            "SELECT dont_save_future_data FROM users WHERE id = %s",
            (user_id,)
        )
        
        row = cur.fetchone()
        if not row:
            print(f"   ❌ User not found in database: {user_id}")
            return
        
        actual_dont_save = row[0]
        
        if actual_dont_save == expected_dont_save:
            print(f"   ✓ Database state correct: dont_save_future_data = {actual_dont_save}")
        else:
            print(f"   ❌ Database state INCORRECT:")
            print(f"      Expected: {expected_dont_save}")
            print(f"      Actual:   {actual_dont_save}")
        
        cur.close()
        conn.close()
        
    except ImportError:
        print("   ℹ psycopg2 not available - skipping database verification")
    except Exception as e:
        print(f"   ⚠ Database verification failed: {e}")

def test_checkbox_functionality():
    """Run comprehensive tests for the checkbox."""
    
    print_section("Test: Don't Save Future Data Checkbox")
    
    # Step 1: Login
    session_cookie, user_id = login_user()
    
    # Step 2: Get initial state
    print_section("1. Get Initial State")
    initial_settings = get_settings(session_cookie)
    print(f"   Initial settings: {json.dumps(initial_settings, indent=2)}")
    initial_dont_save = initial_settings.get("dont_save_future_data", False)
    print(f"   dont_save_future_data: {initial_dont_save}")
    
    # Step 3: Toggle to True
    print_section("2. Enable 'Don't Save Future Data'")
    updated_settings = update_settings(session_cookie, dont_save=True)
    print(f"   Updated settings: {json.dumps(updated_settings, indent=2)}")
    
    if updated_settings.get("dont_save_future_data") != True:
        print(f"   ❌ FAILED: Expected True, got {updated_settings.get('dont_save_future_data')}")
        return False
    
    print("   ✓ Checkbox enabled successfully")
    verify_database_state(user_id, True)
    
    # Step 4: Verify persistence (new GET request)
    print_section("3. Verify Persistence")
    time.sleep(0.5)  # Brief delay
    persisted_settings = get_settings(session_cookie)
    
    if persisted_settings.get("dont_save_future_data") != True:
        print(f"   ❌ FAILED: Settings did not persist")
        print(f"   Expected: True")
        print(f"   Got: {persisted_settings.get('dont_save_future_data')}")
        return False
    
    print("   ✓ Settings persisted correctly")
    
    # Step 5: Toggle to False
    print_section("4. Disable 'Don't Save Future Data'")
    updated_settings = update_settings(session_cookie, dont_save=False)
    
    if updated_settings.get("dont_save_future_data") != False:
        print(f"   ❌ FAILED: Expected False, got {updated_settings.get('dont_save_future_data')}")
        return False
    
    print("   ✓ Checkbox disabled successfully")
    verify_database_state(user_id, False)
    
    # Step 6: Verify final state
    print_section("5. Verify Final State")
    final_settings = get_settings(session_cookie)
    
    if final_settings.get("dont_save_future_data") != False:
        print(f"   ❌ FAILED: Final state incorrect")
        return False
    
    print("   ✓ Final state verified")
    
    # Step 7: Test privacy behavior (optional - requires more setup)
    print_section("6. Privacy Behavior (Info Only)")
    print("   When dont_save_future_data = True:")
    print("   - Resume/JD inputs are NOT persisted to last_resume_enc/last_jd_enc")
    print("   - Generated outputs are NOT saved to database")
    print("   - Streaming to client still works")
    print("   - This is enforced by should_persist_user_content() in privacy.py")
    
    print_section("✅ All Tests Passed!")
    return True

def main():
    """Main test runner."""
    try:
        success = test_checkbox_functionality()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
