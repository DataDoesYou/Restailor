"""E2E test: Applied checkbox MUST update database immediately.

This test verifies Steam-like architecture: when user toggles Applied checkbox,
the database is updated within milliseconds (accounting for network latency).

Test Flow:
1. Create test user and login
2. Apply a job (check Applied)
3. Verify database shows is_applied=true immediately
4. Unapply the job (uncheck Applied)
5. Verify database shows is_applied=false immediately
6. Cleanup: Delete all test rows
"""

from __future__ import annotations

import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests
import psycopg2

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8102"))
BACKEND_URL = os.environ.get("BACKEND_BASE_URL", f"http://127.0.0.1:{BACKEND_PORT}")

# Database connection
DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
DB_NAME = os.environ.get("POSTGRES_DB", "restailor")
DB_USER = os.environ.get("POSTGRES_USER", "postgres")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")


def wait_http(url: str, timeout_s: float = 60.0) -> None:
    """Wait for HTTP endpoint to respond."""
    t0 = time.time()
    last_err: Exception | None = None
    while time.time() - t0 < timeout_s:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code < 500:
                return
        except requests.RequestException as ex:
            last_err = ex
        time.sleep(0.5)
    raise RuntimeError(f"Service at {url} not ready: {last_err}")


def get_db_connection():
    """Get PostgreSQL database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


def check_db_applied_state(conn, user_id: int, jd_hash: str) -> bool | None:
    """Check is_applied state in database for given user and JD hash.
    
    Returns:
        True if is_applied=true
        False if is_applied=false
        None if no row found
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT is_applied FROM applications WHERE user_id = %s AND jd_hash = %s ORDER BY updated_at DESC LIMIT 1",
            (user_id, jd_hash)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return bool(row[0])


def cleanup_test_user(conn, email: str):
    """Delete test user and all associated data."""
    with conn.cursor() as cur:
        # Get user_id first
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if row is None:
            return
        user_id = row[0]
        
        # Delete in correct order (respecting foreign keys)
        cur.execute("DELETE FROM analytics_job_snapshot_state WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM applications WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM jobs WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        print(f"✓ Cleaned up test user: {email} (user_id={user_id})")


def main() -> int:
    """Run E2E test for Applied checkbox database updates."""
    env = os.environ.copy()
    env.update({
        "E2E_TEST_MODE": "1",
        "LOGIN_CAPTCHA_REQUIRED": "0",
        "SIGNUP_CAPTCHA_REQUIRED": "0",
        "STRICT_SECRETS": "0",
        "DISABLE_REDIS": os.environ.get("DISABLE_REDIS", "1"),
    })
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    # Start backend server
    print(f"Starting backend server on port {BACKEND_PORT}...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(BACKEND_PORT)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    
    conn = None
    test_email = f"e2e-applied-{secrets.token_hex(6)}@test.local"
    
    try:
        # Wait for backend to be ready
        print(f"Waiting for {BACKEND_URL}/health...")
        wait_http(f"{BACKEND_URL}/health", timeout_s=30.0)
        print("✓ Backend is ready")
        
        # Connect to database
        print("Connecting to database...")
        conn = get_db_connection()
        print("✓ Database connected")
        
        # Step 1: Create test user
        print(f"\n1. Creating test user: {test_email}")
        signup_resp = requests.post(
            f"{BACKEND_URL}/auth/signup",
            json={
                "email": test_email,
                "password": "TestPassword123!",
                "name": "E2E Applied Test User"
            },
            timeout=10
        )
        assert signup_resp.status_code == 200, f"Signup failed: {signup_resp.status_code} {signup_resp.text}"
        print(f"✓ User created")
        
        # Step 2: Login
        print(f"\n2. Logging in...")
        login_resp = requests.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": test_email, "password": "TestPassword123!"},
            timeout=10
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.status_code} {login_resp.text}"
        session_cookie = login_resp.cookies.get("session")
        assert session_cookie, "No session cookie returned"
        cookies = {"session": session_cookie}
        print(f"✓ Logged in")
        
        # Get user_id
        me_resp = requests.get(f"{BACKEND_URL}/auth/me", cookies=cookies, timeout=10)
        assert me_resp.status_code == 200
        user_id = me_resp.json()["id"]
        print(f"✓ User ID: {user_id}")
        
        # Step 3: Apply a job (POST /applications/jd/apply)
        print(f"\n3. Applying a job...")
        jd_text = "E2E Test Job: Software Engineer position requiring Python and PostgreSQL"
        resume_text = "E2E Test Resume: Experienced software engineer with Python and PostgreSQL"
        
        apply_start = time.time()
        apply_resp = requests.post(
            f"{BACKEND_URL}/applications/jd/apply",
            json={
                "jdText": jd_text,
                "baseText": resume_text,
                "snapshot": {
                    "resumeInput": resume_text,
                    "jdInput": jd_text,
                    "fitOutput": "E2E test fit output",
                    "tailoredOutput": "E2E test tailored output",
                },
                "consent": True
            },
            cookies=cookies,
            timeout=30
        )
        apply_duration = (time.time() - apply_start) * 1000
        assert apply_resp.status_code == 200, f"Apply failed: {apply_resp.status_code} {apply_resp.text}"
        apply_data = apply_resp.json()
        jd_hash = apply_data["jdHash"]
        applied_key = apply_data["appliedKey"]
        db_is_applied_from_response = apply_data.get("isApplied")
        print(f"✓ Applied job (took {apply_duration:.2f}ms)")
        print(f"  jdHash: {jd_hash[:20]}...")
        print(f"  appliedKey: {applied_key[:30]}...")
        print(f"  Response isApplied: {db_is_applied_from_response}")
        
        # Step 4: Verify database shows is_applied=true IMMEDIATELY
        print(f"\n4. Verifying database state IMMEDIATELY after apply...")
        db_check_start = time.time()
        db_is_applied = check_db_applied_state(conn, user_id, jd_hash)
        db_check_duration = (time.time() - db_check_start) * 1000
        print(f"  Database query took: {db_check_duration:.2f}ms")
        print(f"  Database is_applied: {db_is_applied}")
        
        assert db_is_applied is not None, "No row found in database after apply"
        assert db_is_applied is True, f"❌ FAIL: Database shows is_applied={db_is_applied}, expected True"
        assert db_is_applied_from_response is True, f"❌ FAIL: Response shows isApplied={db_is_applied_from_response}, expected True"
        print(f"✓ PASS: Database correctly shows is_applied=true")
        
        # Step 5: Unapply the job (DELETE /applications/jd/apply)
        print(f"\n5. Unapplying the job...")
        unapply_start = time.time()
        unapply_resp = requests.delete(
            f"{BACKEND_URL}/applications/jd/apply",
            params={"jdHash": jd_hash, "appliedKey": applied_key},
            cookies=cookies,
            timeout=30
        )
        unapply_duration = (time.time() - unapply_start) * 1000
        assert unapply_resp.status_code == 200, f"Unapply failed: {unapply_resp.status_code} {unapply_resp.text}"
        unapply_data = unapply_resp.json()
        db_is_applied_from_response_after_unapply = unapply_data.get("isApplied")
        print(f"✓ Unapplied job (took {unapply_duration:.2f}ms)")
        print(f"  Response isApplied: {db_is_applied_from_response_after_unapply}")
        
        # Step 6: Verify database shows is_applied=false IMMEDIATELY
        print(f"\n6. Verifying database state IMMEDIATELY after unapply...")
        db_check_start = time.time()
        db_is_applied_after = check_db_applied_state(conn, user_id, jd_hash)
        db_check_duration = (time.time() - db_check_start) * 1000
        print(f"  Database query took: {db_check_duration:.2f}ms")
        print(f"  Database is_applied: {db_is_applied_after}")
        
        assert db_is_applied_after is not None, "No row found in database after unapply"
        assert db_is_applied_after is False, f"❌ FAIL: Database shows is_applied={db_is_applied_after}, expected False"
        assert db_is_applied_from_response_after_unapply is False, f"❌ FAIL: Response shows isApplied={db_is_applied_from_response_after_unapply}, expected False"
        print(f"✓ PASS: Database correctly shows is_applied=false")
        
        # Step 7: Verify cascade (IOH flags should be cleared)
        print(f"\n7. Verifying cascade: IOH flags should be false...")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_applied, is_interviewing, is_offer, is_hired FROM applications WHERE user_id = %s AND jd_hash = %s ORDER BY updated_at DESC LIMIT 1",
                (user_id, jd_hash)
            )
            row = cur.fetchone()
            assert row is not None
            is_applied, is_interviewing, is_offer, is_hired = row
            print(f"  is_applied: {is_applied}")
            print(f"  is_interviewing: {is_interviewing}")
            print(f"  is_offer: {is_offer}")
            print(f"  is_hired: {is_hired}")
            
            assert is_applied is False, f"❌ FAIL: is_applied={is_applied}, expected False"
            assert is_interviewing is False, f"❌ FAIL: is_interviewing={is_interviewing}, expected False (cascade)"
            assert is_offer is False, f"❌ FAIL: is_offer={is_offer}, expected False (cascade)"
            assert is_hired is False, f"❌ FAIL: is_hired={is_hired}, expected False (cascade)"
        print(f"✓ PASS: All flags correctly cleared (cascade works)")
        
        print(f"\n✅ ALL TESTS PASSED!")
        print(f"\nSummary:")
        print(f"  Apply request: {apply_duration:.2f}ms")
        print(f"  Unapply request: {unapply_duration:.2f}ms")
        print(f"  Database is IMMEDIATELY updated after mutations ✓")
        
        return 0
        
    except Exception as ex:
        print(f"\n❌ TEST FAILED: {ex}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        # Cleanup: Delete test user and all associated data
        print(f"\n8. Cleanup: Deleting test user and data...")
        if conn:
            try:
                cleanup_test_user(conn, test_email)
            except Exception as ex:
                print(f"Warning: Cleanup failed: {ex}", file=sys.stderr)
            finally:
                conn.close()
        
        # Stop backend server
        if backend_proc:
            print(f"Stopping backend server...")
            backend_proc.send_signal(signal.SIGTERM)
            try:
                backend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_proc.kill()
                backend_proc.wait()
            print(f"✓ Backend stopped")


if __name__ == "__main__":
    sys.exit(main())
