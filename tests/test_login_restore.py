#!/usr/bin/env python3
"""
Test script to verify that login restore functionality works correctly.

Flow:
1. Create/login user
2. Save a snapshot with JD and resume
3. Logout
4. Login again
5. Verify /applications/latest returns the snapshot
"""

import requests
import json
import sys
from datetime import datetime

API_BASE = "http://localhost:8000"
TEST_EMAIL = f"test+restore@example.com"  # Use a consistent email for easier testing
TEST_PASSWORD = "TestPass123!"

def create_and_login_user():
    """Create user and login to get session."""
    print(f"🔐 Logging in as: {TEST_EMAIL}")
    
    # Try to login first (user might already exist)
    resp = requests.post(
        f"{API_BASE}/token",
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    if resp.status_code == 200:
        session_cookie = resp.cookies.get("rt_session")
        if session_cookie:
            print(f"   ✓ Logged in with existing user")
            return session_cookie
    
    # User doesn't exist, create it
    print(f"   Creating new user...")
    resp = requests.post(
        f"{API_BASE}/signup",
        json={"username": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if resp.status_code != 200:
        print(f"   ❌ Signup failed: {resp.status_code} - {resp.text}")
        sys.exit(1)
    print(f"   ✓ User created")
    
    # Try login again
    resp = requests.post(
        f"{API_BASE}/token",
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if resp.status_code != 200:
        print(f"   ❌ Login failed: {resp.status_code} - {resp.text}")
        print(f"   ⚠ You may need to verify the user manually:")
        print(f"   docker exec restailor-postgres-1 psql -U postgres -d restailor -c \"UPDATE users SET email_verified=true WHERE username='{TEST_EMAIL}';\"")
        sys.exit(1)
    
    session_cookie = resp.cookies.get("rt_session")
    if not session_cookie:
        print(f"   ❌ No session cookie received")
        sys.exit(1)
    
    print(f"   ✓ Logged in successfully")
    return session_cookie


def save_snapshot(session_cookie):
    """Save a snapshot with JD and resume."""
    print("\n💾 Saving snapshot...")
    
    snapshot_data = {
        "jdText": "Senior Python Developer position at TechCorp. Must have 5+ years experience.",
        "baseText": "John Doe\nSenior Software Engineer\n10 years experience in Python development.",
        "snapshot": {
            "resumeInput": "John Doe\nSenior Software Engineer\n10 years experience in Python development.",
            "jdInput": "Senior Python Developer position at TechCorp. Must have 5+ years experience.",
            "fitOutput": "Strong fit! Your 10 years experience exceeds the 5 year requirement.",
            "tailoredOutput": "JOHN DOE\nSENIOR PYTHON DEVELOPER\n\nProfessional Summary:\nHighly experienced Python developer with 10 years of expertise...",
            "judgeOutput": "8/10 - Excellent match. Strong technical background.",
            "statsMd": "Fit time: 2.3s\nTailor time: 3.1s\nJudge time: 1.8s",
            "knobs": {
                "fitModelLabel": "GPT-4o",
                "tailorModelLabel": "Claude 3.5 Sonnet",
                "judgeLabel": "Judge: GPT-4o"
            },
            "modelInfo": {
                "provider": "openai",
                "model": "gpt-4o"
            }
        }
    }
    
    resp = requests.post(
        f"{API_BASE}/applications/jd/save",
        json=snapshot_data,
        cookies={"rt_session": session_cookie}
    )
    
    if resp.status_code != 200:
        print(f"   ❌ Save failed: {resp.status_code} - {resp.text}")
        sys.exit(1)
    
    result = resp.json()
    print(f"   ✓ Snapshot saved")
    print(f"   - JD Hash: {result.get('jdHash', 'N/A')[:16]}...")
    print(f"   - Applied Key: {result.get('appliedKey', 'N/A')[:20]}...")
    return result


def logout(session_cookie):
    """Logout user."""
    print("\n👋 Logging out...")
    
    resp = requests.post(
        f"{API_BASE}/logout",
        cookies={"rt_session": session_cookie}
    )
    
    if resp.status_code != 200:
        print(f"   ⚠ Logout returned {resp.status_code} (may be OK)")
    else:
        print(f"   ✓ Logged out")


def verify_latest_snapshot(session_cookie):
    """Verify /applications/latest returns the saved snapshot."""
    print("\n🔍 Verifying /applications/latest...")
    
    resp = requests.get(
        f"{API_BASE}/applications/latest",
        cookies={"rt_session": session_cookie}
    )
    
    if resp.status_code != 200:
        print(f"   ❌ Request failed: {resp.status_code} - {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    
    if not data.get("found"):
        print(f"   ❌ No snapshot found!")
        sys.exit(1)
    
    print(f"   ✓ Snapshot found")
    
    # Verify data
    snapshot = data.get("snapshot", {})
    checks = [
        ("Resume Input", snapshot.get("resumeInput", "").startswith("John Doe")),
        ("JD Input", "TechCorp" in snapshot.get("jdInput", "")),
        ("Fit Output", "Strong fit" in snapshot.get("fitOutput", "")),
        ("Tailored Output", "JOHN DOE" in snapshot.get("tailoredOutput", "")),
        ("Judge Output", "8/10" in snapshot.get("judgeOutput", "")),
        ("Stats", "Fit time" in snapshot.get("statsMd", "")),
        ("Model Knobs", snapshot.get("knobs", {}).get("fitModelLabel") == "GPT-4o"),
    ]
    
    all_passed = True
    for check_name, passed in checks:
        status = "✓" if passed else "❌"
        print(f"   {status} {check_name}: {passed}")
        if not passed:
            all_passed = False
    
    if not all_passed:
        print(f"\n❌ Some checks failed!")
        print(f"\nFull response:")
        print(json.dumps(data, indent=2))
        sys.exit(1)
    
    return data


def main():
    """Run the test flow."""
    print("=" * 60)
    print("Testing Login Restore Functionality")
    print("=" * 60)
    
    # Step 1: Create and login
    session_cookie = create_and_login_user()
    
    # Step 2: Save snapshot
    save_result = save_snapshot(session_cookie)
    
    # Step 3: Logout
    logout(session_cookie)
    
    # Step 4: Login again
    print("\n🔐 Logging in again...")
    resp = requests.post(
        f"{API_BASE}/token",
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if resp.status_code != 200:
        print(f"   ❌ Re-login failed: {resp.status_code}")
        sys.exit(1)
    
    new_session_cookie = resp.cookies.get("rt_session")
    print(f"   ✓ Logged in again")
    
    # Step 5: Verify latest snapshot
    latest_data = verify_latest_snapshot(new_session_cookie)
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nSummary:")
    print(f"  - User can save snapshots")
    print(f"  - After logout and login, /applications/latest returns the snapshot")
    print(f"  - All data (inputs, outputs, stats, model selections) is preserved")
    print(f"\n🎉 Login restore functionality is working correctly!")


if __name__ == "__main__":
    main()
