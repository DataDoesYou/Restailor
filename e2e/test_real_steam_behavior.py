#!/usr/bin/env python3
"""
E2E Test: REAL Steam-like behavior test with IMMEDIATE navigation

This test simulates the ACTUAL user behavior:
1. Click checkbox (start request)
2. IMMEDIATELY navigate (don't wait for response)
3. Check database

The previous test was flawed - it waited for the response.
This test uses threading to simulate clicking the checkbox and
IMMEDIATELY checking the database without waiting.
"""

import sys
import time
import requests
import psycopg2
import os
import threading
from typing import Dict, Any

# Configuration
BACKEND_URL = "http://localhost:8000"
TEST_EMAIL = f"realsteamtest_{int(time.time())}@example.com"
TEST_PASSWORD = "TestPassword123!"

def get_db_connection():
    """Get database connection using environment variables (Doppler format)."""
    db_host = os.environ.get("POSTGRES_HOST") or os.environ.get("DB_HOST", "localhost")
    if db_host == "postgres":
        db_host = "localhost"
    
    db_port = int(os.environ.get("DB_PORT") or os.environ.get("POSTGRES_PORT", "5432"))
    db_name = os.environ.get("DB_NAME") or os.environ.get("POSTGRES_DB")
    db_user = os.environ.get("DB_USER") or os.environ.get("POSTGRES_USER")
    db_password = os.environ.get("DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD")
    
    if not all([db_host, db_name, db_user, db_password]):
        raise Exception("Missing database credentials! Run with: doppler run -- poetry run python e2e/test_real_steam_behavior.py")
    
    return psycopg2.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_password,
    )

def check_db_applied_state(conn, user_id: int, jd_hash: str) -> tuple[bool, str]:
    """Check if a job is marked as applied in database. Returns (is_applied, timestamp)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT is_applied, updated_at FROM applications WHERE user_id = %s AND jd_hash = %s ORDER BY updated_at DESC LIMIT 1",
        (user_id, jd_hash)
    )
    result = cur.fetchone()
    cur.close()
    if not result:
        return False, "never"
    return result[0], str(result[1])

def cleanup_test_user(conn, email: str):
    """Delete test user and all their data."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE username = %s", (email,))
        result = cur.fetchone()
        if not result:
            return
        user_id = result[0]
        
        cur.execute("DELETE FROM applications WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM analytics_job_snapshot_state WHERE user_id = %s", (user_id,))
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
    print("🧪 REAL STEAM TEST: Immediate Navigation")
    print("="*70 + "\n")
    
    conn = None
    
    try:
        # Setup
        print("📊 Connecting to database...")
        conn = get_db_connection()
        print("✓ Database connected\n")
        
        # Create and verify user
        print("1️⃣  Creating test user...")
        signup_resp = requests.post(
            f"{BACKEND_URL}/signup",
            json={"username": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"X-Client-Id": "real-steam-e2e"},
            timeout=10
        )
        
        if signup_resp.status_code != 200:
            print(f"❌ Signup failed: {signup_resp.status_code} {signup_resp.text}")
            return 1
        
        # Mark verified and get user_id
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_verified = true WHERE username = %s", (TEST_EMAIL,))
        conn.commit()
        cur.execute("SELECT id FROM users WHERE username = %s", (TEST_EMAIL,))
        result = cur.fetchone()
        if not result:
            print(f"❌ Failed to find user in database")
            return 1
        user_id = result[0]
        cur.close()
        print(f"✓ User created and verified (ID={user_id})\n")
        
        # Login
        print("2️⃣  Logging in...")
        login_resp = requests.post(
            f"{BACKEND_URL}/token",
            data={"username": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        
        if login_resp.status_code != 200:
            print(f"❌ Login failed: {login_resp.status_code}")
            return 1
        
        access_token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        print("✓ Logged in\n")
        
        # Prepare job data
        jd_text = "Senior Software Engineer position requiring Python and FastAPI experience."
        base_text = "Experienced software engineer with Python expertise."
        
        import hashlib
        jd_hash = hashlib.sha256(jd_text.encode()).hexdigest()
        
        snapshot = {
            "resumeInput": base_text,
            "jdInput": jd_text,
            "fitOutput": None,
            "tailoredOutput": None,
            "judgeOutput": None,
            "statsMd": None,
            "knobs": {},
            "modelInfo": {"provider": "test", "model": "test"}
        }
        
        # ==================================================================
        # TEST 1: Apply with IMMEDIATE database check (no waiting!)
        # ==================================================================
        print("3️⃣  REAL STEAM TEST #1: APPLY with immediate navigation")
        print("   (Simulating: Click checkbox → INSTANT History navigation)\n")
        
        # Variable to store when request actually completes
        request_complete_time: list = [None]
        request_error: list = [None]
        
        def make_apply_request():
            """Background thread: Make the apply request."""
            try:
                start = time.time()
                resp = requests.post(
                    f"{BACKEND_URL}/applications/jd/apply",
                    json={
                        "jdText": jd_text,
                        "baseText": base_text,
                        "snapshot": snapshot,
                        "consent": True
                    },
                    headers=headers,
                    timeout=10
                )
                request_complete_time[0] = time.time() - start
                if resp.status_code != 200:
                    request_error[0] = f"Status {resp.status_code}: {resp.text}"
            except Exception as e:
                request_error[0] = str(e)
        
        # Start the request in background (simulates clicking checkbox)
        thread = threading.Thread(target=make_apply_request)
        thread.start()
        
        # IMMEDIATELY check database (simulates navigating to History page)
        # Wait only 1ms to let request START, then check DB
        time.sleep(0.001)  # 1ms - just to ensure request thread started
        
        print("   ⚡ Checking database IMMEDIATELY (simulating instant navigation)...")
        db_is_applied_instant, db_timestamp_instant = check_db_applied_state(conn, user_id, jd_hash)
        
        print(f"   📊 Database at 1ms: is_applied={db_is_applied_instant}")
        
        # Now wait for request to complete
        thread.join(timeout=5)
        
        if request_error[0]:
            print(f"\n❌ Request error: {request_error[0]}")
            return 1
        
        print(f"   ⏱️  Request completed in: {request_complete_time[0]*1000:.2f}ms")
        
        # Check database again after request completes
        time.sleep(0.01)  # 10ms grace period
        db_is_applied_final, db_timestamp_final = check_db_applied_state(conn, user_id, jd_hash)
        
        print(f"   📊 Database after request: is_applied={db_is_applied_final}\n")
        
        # EVALUATION
        if db_is_applied_instant:
            print("   ✅ PASS: Database updated BEFORE response returned!")
            print("      Steam-like behavior: PERFECT! 🚀")
        elif db_is_applied_final:
            print("   ⚠️  PARTIAL: Database updated, but NOT before response")
            print(f"      Request took {request_complete_time[0]*1000:.2f}ms")
            print("      Database was updated AFTER the request completed")
            print("      If user navigates instantly, they'll see STALE data!")
            print("\n   ❌ FAIL: NOT Steam-like behavior!")
            return 1
        else:
            print("   ❌ FAIL: Database never updated!")
            return 1
        
        # ==================================================================
        # TEST 2: Unapply with IMMEDIATE database check
        # ==================================================================
        print("\n4️⃣  REAL STEAM TEST #2: UNAPPLY with immediate navigation\n")
        
        request_complete_time[0] = None
        request_error[0] = None
        
        def make_unapply_request():
            """Background thread: Make the unapply request."""
            try:
                start = time.time()
                resp = requests.delete(
                    f"{BACKEND_URL}/applications/jd/apply",
                    params={"jdHash": jd_hash},
                    headers=headers,
                    timeout=10
                )
                request_complete_time[0] = time.time() - start
                if resp.status_code != 200:
                    request_error[0] = f"Status {resp.status_code}: {resp.text}"
            except Exception as e:
                request_error[0] = str(e)
        
        # Start unapply request
        thread = threading.Thread(target=make_unapply_request)
        thread.start()
        
        # IMMEDIATELY check database
        time.sleep(0.001)  # 1ms
        
        print("   ⚡ Checking database IMMEDIATELY (simulating instant navigation)...")
        db_is_applied_instant2, _ = check_db_applied_state(conn, user_id, jd_hash)
        
        print(f"   📊 Database at 1ms: is_applied={db_is_applied_instant2}")
        
        # Wait for request
        thread.join(timeout=5)
        
        if request_error[0]:
            print(f"\n❌ Request error: {request_error[0]}")
            return 1
        
        print(f"   ⏱️  Request completed in: {request_complete_time[0]*1000:.2f}ms")
        
        # Check final state
        time.sleep(0.01)
        db_is_applied_final2, _ = check_db_applied_state(conn, user_id, jd_hash)
        
        print(f"   📊 Database after request: is_applied={db_is_applied_final2}\n")
        
        # EVALUATION
        if not db_is_applied_instant2:
            print("   ✅ PASS: Database updated BEFORE response returned!")
            print("      Steam-like behavior: PERFECT! 🚀")
        elif not db_is_applied_final2:
            print("   ⚠️  PARTIAL: Database updated, but NOT before response")
            print(f"      Request took {request_complete_time[0]*1000:.2f}ms")
            print("      Database was updated AFTER the request completed")
            print("      If user navigates instantly, they'll see STALE data!")
            print("\n   ❌ FAIL: NOT Steam-like behavior!")
            return 1
        else:
            print("   ❌ FAIL: Database never updated!")
            return 1
        
        # Cleanup
        print("\n5️⃣  Cleaning up...")
        cleanup_test_user(conn, TEST_EMAIL)
        
        # Final verdict
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED - TRUE STEAM BEHAVIOR!")
        print("="*70)
        print("\n💡 Database updates happen BEFORE response returns")
        print("   Users can navigate INSTANTLY without seeing stale data")
        print("   This is the REAL Steam standard! 🎮✨\n")
        
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
