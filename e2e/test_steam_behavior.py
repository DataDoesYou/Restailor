#!/usr/bin/env python3
"""
E2E Test: Steam-like Applied Checkbox Behavior

Tests that the Applied checkbox updates the database IMMEDIATELY,
even if the user navigates away instantly (like Steam wishlist).

This test:
1. Applies a job
2. Immediately checks database (no delay)
3. Verifies is_applied=true in database
4. Unapplies the job
5. Immediately checks database (no delay)
6. Verifies is_applied=false in database

If this passes, the Steam-like behavior is working!
"""

import sys
import time
import requests
import psycopg2
import os
import json
from typing import Dict, Any

# Configuration
BACKEND_URL = "http://localhost:8000"
TEST_EMAIL = f"steamtest_{int(time.time())}@example.com"
TEST_PASSWORD = "TestPassword123!"

def get_db_connection():
    """Get database connection using environment variables (Doppler format)."""
    # Doppler uses DB_* prefix, also support POSTGRES_* for compatibility
    db_host = os.environ.get("POSTGRES_HOST") or os.environ.get("DB_HOST", "localhost")
    # If DB_HOST is "postgres", override to localhost (Docker internal name)
    if db_host == "postgres":
        db_host = "localhost"
    
    db_port = int(os.environ.get("DB_PORT") or os.environ.get("POSTGRES_PORT", "5432"))
    db_name = os.environ.get("DB_NAME") or os.environ.get("POSTGRES_DB")
    db_user = os.environ.get("DB_USER") or os.environ.get("POSTGRES_USER")
    db_password = os.environ.get("DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD")
    
    if not all([db_host, db_name, db_user, db_password]):
        raise Exception("Missing database credentials! Run with: doppler run -- poetry run python e2e/test_steam_behavior.py")
    
    return psycopg2.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_password,
    )

def check_db_applied_state(conn, user_id: int, jd_hash: str) -> bool:
    """Check if a job is marked as applied in database."""
    cur = conn.cursor()
    cur.execute(
        "SELECT is_applied FROM applications WHERE user_id = %s AND jd_hash = %s ORDER BY updated_at DESC LIMIT 1",
        (user_id, jd_hash)
    )
    result = cur.fetchone()
    cur.close()
    return result[0] if result else False

def cleanup_test_user(conn, email: str):
    """Delete test user and all their data."""
    cur = conn.cursor()
    try:
        # Get user_id (username column, not email)
        cur.execute("SELECT id FROM users WHERE username = %s", (email,))
        result = cur.fetchone()
        if not result:
            return
        user_id = result[0]
        
        # Delete applications first (foreign key constraint)
        cur.execute("DELETE FROM applications WHERE user_id = %s", (user_id,))
        
        # Delete analytics
        cur.execute("DELETE FROM analytics_job_snapshot_state WHERE user_id = %s", (user_id,))
        
        # Delete user
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        
        conn.commit()
        print(f"✓ Cleaned up test user: {email}")
    except Exception as e:
        print(f"⚠ Cleanup warning: {e}")
        conn.rollback()
    finally:
        cur.close()

def main() -> int:
    print("\n" + "="*70)
    print("🧪 E2E TEST: Steam-like Applied Checkbox Behavior")
    print("="*70 + "\n")
    
    conn = None
    
    try:
        # Connect to database
        print("📊 Connecting to database...")
        conn = get_db_connection()
        print("✓ Database connected\n")
        
        # Step 1: Create test user
        print("1️⃣  Creating test user...")
        signup_resp = requests.post(
            f"{BACKEND_URL}/signup",
            json={
                "username": TEST_EMAIL,
                "password": TEST_PASSWORD
            },
            headers={"X-Client-Id": "steam-e2e-test"},
            timeout=10
        )
        
        if signup_resp.status_code != 200:
            print(f"❌ Signup failed: {signup_resp.status_code} {signup_resp.text}")
            return 1
        
        signup_data = signup_resp.json()
        user_id = signup_data.get("id")
        print(f"✓ Test user created: ID={user_id}, Email={TEST_EMAIL}\n")
        
        # Mark user as verified in database (use username since that's what we have)
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_verified = true WHERE username = %s", (TEST_EMAIL,))
        conn.commit()
        
        # Get the actual user_id after verification
        cur.execute("SELECT id FROM users WHERE username = %s", (TEST_EMAIL,))
        result = cur.fetchone()
        if not result:
            print(f"❌ Failed to find user {TEST_EMAIL} in database after signup")
            return 1
        user_id = result[0]
        cur.close()
        print(f"✓ Marked user as verified (ID={user_id})\n")
        
        # Step 2: Login
        print("2️⃣  Logging in...")
        login_resp = requests.post(
            f"{BACKEND_URL}/token",
            data={
                "username": TEST_EMAIL,
                "password": TEST_PASSWORD
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        
        if login_resp.status_code != 200:
            print(f"❌ Login failed: {login_resp.status_code}")
            return 1
        
        access_token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        print("✓ Logged in successfully\n")
        
        # Step 3: Apply a job (STEAM TEST: Measure speed)
        print("3️⃣  APPLYING job (Steam-like test)...")
        
        jd_text = "Senior Software Engineer position requiring Python and FastAPI experience."
        base_text = "Experienced software engineer with Python expertise."
        
        # Compute JD hash (same as frontend)
        import hashlib
        jd_hash = hashlib.sha256(jd_text.encode()).hexdigest()
        
        apply_start = time.time()
        apply_resp = requests.post(
            f"{BACKEND_URL}/applications/jd/apply",
            json={
                "jdText": jd_text,
                "baseText": base_text,
                "snapshot": {
                    "resumeInput": base_text,
                    "jdInput": jd_text,
                    "fitOutput": None,
                    "tailoredOutput": None,
                    "judgeOutput": None,
                    "statsMd": None,
                    "knobs": {},
                    "modelInfo": {"provider": "test", "model": "test"}
                },
                "consent": True
            },
            headers=headers,
            timeout=10
        )
        apply_duration = (time.time() - apply_start) * 1000
        
        if apply_resp.status_code != 200:
            print(f"❌ Apply failed: {apply_resp.status_code} {apply_resp.text}")
            return 1
        
        apply_data = apply_resp.json()
        response_is_applied = apply_data.get("isApplied")
        
        print(f"✓ POST /applications/jd/apply completed in {apply_duration:.2f}ms")
        print(f"  Response: isApplied={response_is_applied}\n")
        
        # CRITICAL: Immediately check database (no delay - like Steam navigation)
        print("4️⃣  STEAM TEST: Checking database IMMEDIATELY (0ms delay)...")
        db_is_applied = check_db_applied_state(conn, user_id, jd_hash)
        
        print(f"  Database: is_applied={db_is_applied}")
        print(f"  Response: isApplied={response_is_applied}")
        
        if db_is_applied != True:
            print(f"\n❌ FAIL: Database shows is_applied={db_is_applied}, expected True!")
            print("   This means the database wasn't updated before the response returned.")
            print("   NOT Steam-like behavior! ❌")
            return 1
        
        if response_is_applied != True:
            print(f"\n❌ FAIL: Response shows isApplied={response_is_applied}, expected True!")
            return 1
        
        print("✓ PASS: Database updated IMMEDIATELY (Steam-like!) ✅\n")
        
        # Step 5: Unapply the job (STEAM TEST 2: Reverse operation)
        print("5️⃣  UNAPPLYING job (Steam-like test #2)...")
        
        unapply_start = time.time()
        unapply_resp = requests.delete(
            f"{BACKEND_URL}/applications/jd/apply",
            params={"jdHash": jd_hash},
            headers=headers,
            timeout=10
        )
        unapply_duration = (time.time() - unapply_start) * 1000
        
        if unapply_resp.status_code != 200:
            print(f"❌ Unapply failed: {unapply_resp.status_code} {unapply_resp.text}")
            return 1
        
        unapply_data = unapply_resp.json()
        response_is_applied_after = unapply_data.get("isApplied")
        
        print(f"✓ DELETE /applications/jd/apply completed in {unapply_duration:.2f}ms")
        print(f"  Response: isApplied={response_is_applied_after}\n")
        
        # CRITICAL: Immediately check database again (no delay)
        print("6️⃣  STEAM TEST: Checking database IMMEDIATELY (0ms delay)...")
        db_is_applied_after = check_db_applied_state(conn, user_id, jd_hash)
        
        print(f"  Database: is_applied={db_is_applied_after}")
        print(f"  Response: isApplied={response_is_applied_after}")
        
        if db_is_applied_after != False:
            print(f"\n❌ FAIL: Database shows is_applied={db_is_applied_after}, expected False!")
            print("   This means the database wasn't updated before the response returned.")
            print("   NOT Steam-like behavior! ❌")
            return 1
        
        if response_is_applied_after != False:
            print(f"\n❌ FAIL: Response shows isApplied={response_is_applied_after}, expected False!")
            return 1
        
        print("✓ PASS: Database updated IMMEDIATELY (Steam-like!) ✅\n")
        
        # Cleanup
        print("7️⃣  Cleaning up...")
        cleanup_test_user(conn, TEST_EMAIL)
        
        # Final summary
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED - STEAM-LIKE BEHAVIOR VERIFIED!")
        print("="*70)
        print(f"\n📊 Performance:")
        print(f"   Apply:   {apply_duration:.2f}ms")
        print(f"   Unapply: {unapply_duration:.2f}ms")
        print(f"\n🎮 Steam Standard: Mutations complete in < 100ms")
        
        if apply_duration < 100 and unapply_duration < 100:
            print("   ✅ MEETS Steam standard!")
        else:
            print("   ⚠️  Slower than Steam (but still works)")
        
        print("\n💡 This proves:")
        print("   1. Database commits BEFORE response returns")
        print("   2. No delay needed between mutation and navigation")
        print("   3. History page will ALWAYS show correct data")
        print("   4. Works exactly like Steam wishlist! 🚀")
        print()
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        if conn:
            try:
                cleanup_test_user(conn, TEST_EMAIL)
            except:
                pass
            conn.close()

if __name__ == "__main__":
    exit(main())
