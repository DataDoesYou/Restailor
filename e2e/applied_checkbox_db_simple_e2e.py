"""E2E test: Applied checkbox MUST update database immediately.

This test uses EXISTING running backend and database.
Verifies Steam-like architecture: database updates immediately on checkbox toggle.

Usage:
    doppler run -- python e2e/applied_checkbox_db_simple_e2e.py
    
    OR with poetry:
    
    doppler run -- poetry run python e2e/applied_checkbox_db_simple_e2e.py

Environment variables (from Doppler):
    BACKEND_URL - Backend URL (default: http://localhost:5000)
    POSTGRES_HOST - Database host
    POSTGRES_PORT - Database port
    POSTGRES_DB - Database name
    POSTGRES_USER - Database user
    POSTGRES_PASSWORD - Database password
"""

from __future__ import annotations

import os
import secrets
import sys
import time

import requests
import psycopg2

# Configuration from Doppler environment
# Doppler uses DB_* prefix, also support POSTGRES_* for compatibility
# Note: DB_HOST from Doppler is "postgres" (Docker internal), override to "localhost" for host machine
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
DB_HOST = os.environ.get("POSTGRES_HOST") or os.environ.get("DB_HOST", "localhost")
# If DB_HOST is "postgres", override to localhost (Docker internal name doesn't work from host)
if DB_HOST == "postgres":
    DB_HOST = "localhost"
DB_PORT = int(os.environ.get("DB_PORT") or os.environ.get("POSTGRES_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME") or os.environ.get("POSTGRES_DB")
DB_USER = os.environ.get("DB_USER") or os.environ.get("POSTGRES_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD")

# Validate required environment variables
if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
    print("❌ ERROR: Missing required database credentials!")
    print("Please run with Doppler:")
    print("  doppler run -- python e2e/applied_checkbox_db_simple_e2e.py")
    print("\nOr set environment variables:")
    print("  DB_HOST, DB_NAME, DB_USER, DB_PASSWORD")
    print("  (or POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)")
    sys.exit(1)


def get_db_connection():
    """Get PostgreSQL database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


def check_db_applied_state(conn, user_id: int, jd_hash: str) -> tuple[bool | None, dict]:
    """Check is_applied state in database.
    
    Returns:
        (is_applied, flags_dict) where is_applied is True/False/None
        flags_dict contains: {is_interviewing, is_offer, is_hired}
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT is_applied, is_interviewing, is_offer, is_hired 
               FROM applications 
               WHERE user_id = %s AND jd_hash = %s 
               ORDER BY updated_at DESC LIMIT 1""",
            (user_id, jd_hash)
        )
        row = cur.fetchone()
        if row is None:
            return None, {}
        return bool(row[0]), {
            "is_interviewing": bool(row[1]),
            "is_offer": bool(row[2]),
            "is_hired": bool(row[3])
        }


def cleanup_test_user(conn, email: str):
    """Delete test user and all associated data."""
    with conn.cursor() as cur:
        # username IS the email column in this system
        cur.execute("SELECT id FROM users WHERE username = %s", (email,))
        row = cur.fetchone()
        if row is None:
            print(f"  No user found with username: {email}")
            return
        user_id = row[0]
        
        # Delete in correct order
        cur.execute("DELETE FROM analytics_job_snapshot_state WHERE user_id = %s", (user_id,))
        deleted_analytics = cur.rowcount
        cur.execute("DELETE FROM applications WHERE user_id = %s", (user_id,))
        deleted_apps = cur.rowcount
        cur.execute("DELETE FROM jobs WHERE user_id = %s", (user_id,))
        deleted_jobs = cur.rowcount
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        print(f"✓ Cleaned up test user: {email}")
        print(f"  Deleted: {deleted_analytics} analytics, {deleted_apps} applications, {deleted_jobs} jobs, user_id={user_id}")


def main() -> int:
    """Run E2E test for Applied checkbox database updates."""
    conn = None
    # username IS the email in this system
    test_email = f"e2e-applied-{secrets.token_hex(6)}@example.com"
    test_username = test_email  # username field expects email format
    
    try:
        # Print configuration
        print(f"Configuration:")
        print(f"  Backend URL: {BACKEND_URL}")
        print(f"  Database: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        print(f"\nUsing backend at {BACKEND_URL}...")
        
        # Connect to database
        print(f"Connecting to database at {DB_HOST}:{DB_PORT}/{DB_NAME}...")
        conn = get_db_connection()
        print(f"✓ Database connected")
        
        # Step 1: Create test user
        print(f"\n1. Creating test user: {test_email}")
        signup_resp = requests.post(
            f"{BACKEND_URL}/signup",
            json={
                "username": test_username,
                "email": test_email,
                "password": "TestPassword123!",
                "cf_turnstile_response": "dummy_for_test"  # CAPTCHA token
            },
            timeout=10
        )
        if signup_resp.status_code not in (200, 201):
            print(f"❌ Signup failed: {signup_resp.status_code}")
            print(f"Response: {signup_resp.text}")
            return 1
        print(f"✓ User created")
        
        # Step 2: Login via OAuth2 token endpoint
        print(f"\n2. Logging in...")
        login_resp = requests.post(
            f"{BACKEND_URL}/token",
            data={
                "username": test_username,
                "password": "TestPassword123!",
                "grant_type": "password"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        if login_resp.status_code != 200:
            print(f"❌ Login failed: {login_resp.status_code}")
            print(f"Response: {login_resp.text}")
            return 1
        token_data = login_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            print(f"❌ No access token returned")
            return 1
        headers = {"Authorization": f"Bearer {access_token}"}
        print(f"✓ Logged in")
        
        # Get user_id from database and mark as verified
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = %s", (test_username,))
            row = cur.fetchone()
            if not row:
                print(f"❌ Could not find user_id for {test_username}")
                return 1
            user_id = row[0]
            
            # Mark user as verified (both flags needed)
            cur.execute(
                "UPDATE users SET is_verified = true, is_email_verified = true WHERE id = %s",
                (user_id,)
            )
            conn.commit()
        print(f"  User ID: {user_id} (verified)")
        print(f"✓ User ID: {user_id}")
        
        # Step 3: Apply a job
        print(f"\n3. Applying a job (POST /applications/jd/apply)...")
        jd_text = f"E2E Test Job {secrets.token_hex(4)}: Software Engineer requiring Python and PostgreSQL"
        resume_text = f"E2E Test Resume {secrets.token_hex(4)}: Experienced engineer with Python and PostgreSQL"
        
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
            headers=headers,
            timeout=30
        )
        apply_duration = (time.time() - apply_start) * 1000
        
        if apply_resp.status_code != 200:
            print(f"❌ Apply failed: {apply_resp.status_code}")
            print(f"Response: {apply_resp.text}")
            return 1
            
        apply_data = apply_resp.json()
        jd_hash = apply_data["jdHash"]
        applied_key = apply_data["appliedKey"]
        response_is_applied = apply_data.get("isApplied")
        
        print(f"✓ Applied job (took {apply_duration:.2f}ms)")
        print(f"  jdHash: {jd_hash[:20]}...")
        print(f"  appliedKey: {applied_key[:30]}...")
        print(f"  Response isApplied: {response_is_applied}")
        
        # Step 4: Verify database IMMEDIATELY
        print(f"\n4. Verifying database state IMMEDIATELY after apply...")
        db_check_start = time.time()
        db_is_applied, flags = check_db_applied_state(conn, user_id, jd_hash)
        db_check_duration = (time.time() - db_check_start) * 1000
        
        print(f"  Database query took: {db_check_duration:.2f}ms")
        print(f"  Database is_applied: {db_is_applied}")
        
        if db_is_applied is None:
            print(f"❌ FAIL: No row found in database after apply!")
            return 1
        if db_is_applied is not True:
            print(f"❌ FAIL: Database shows is_applied={db_is_applied}, expected True!")
            return 1
        if response_is_applied is not True:
            print(f"❌ FAIL: Response shows isApplied={response_is_applied}, expected True!")
            return 1
            
        print(f"✓ PASS: Database correctly shows is_applied=true")
        
        # Step 5: Unapply the job
        print(f"\n5. Unapplying the job (DELETE /applications/jd/apply)...")
        unapply_start = time.time()
        unapply_resp = requests.delete(
            f"{BACKEND_URL}/applications/jd/apply",
            params={"jdHash": jd_hash, "appliedKey": applied_key},
            headers=headers,
            timeout=30
        )
        unapply_duration = (time.time() - unapply_start) * 1000
        
        if unapply_resp.status_code != 200:
            print(f"❌ Unapply failed: {unapply_resp.status_code}")
            print(f"Response: {unapply_resp.text}")
            return 1
            
        unapply_data = unapply_resp.json()
        response_is_applied_after = unapply_data.get("isApplied")
        
        print(f"✓ Unapplied job (took {unapply_duration:.2f}ms)")
        print(f"  Response isApplied: {response_is_applied_after}")
        
        # Step 6: Verify database IMMEDIATELY
        print(f"\n6. Verifying database state IMMEDIATELY after unapply...")
        db_check_start = time.time()
        db_is_applied_after, flags_after = check_db_applied_state(conn, user_id, jd_hash)
        db_check_duration = (time.time() - db_check_start) * 1000
        
        print(f"  Database query took: {db_check_duration:.2f}ms")
        print(f"  Database is_applied: {db_is_applied_after}")
        print(f"  Database is_interviewing: {flags_after.get('is_interviewing')}")
        print(f"  Database is_offer: {flags_after.get('is_offer')}")
        print(f"  Database is_hired: {flags_after.get('is_hired')}")
        
        if db_is_applied_after is None:
            print(f"❌ FAIL: No row found in database after unapply!")
            return 1
        if db_is_applied_after is not False:
            print(f"❌ FAIL: Database shows is_applied={db_is_applied_after}, expected False!")
            print(f"\n🔥 THIS IS THE BUG: Database was NOT updated after DELETE request!")
            return 1
        if response_is_applied_after is not False:
            print(f"❌ FAIL: Response shows isApplied={response_is_applied_after}, expected False!")
            return 1
            
        # Verify cascade
        if flags_after.get("is_interviewing") is not False:
            print(f"❌ FAIL: is_interviewing not cleared (cascade failed)")
            return 1
        if flags_after.get("is_offer") is not False:
            print(f"❌ FAIL: is_offer not cleared (cascade failed)")
            return 1
        if flags_after.get("is_hired") is not False:
            print(f"❌ FAIL: is_hired not cleared (cascade failed)")
            return 1
            
        print(f"✓ PASS: Database correctly shows is_applied=false")
        print(f"✓ PASS: All IOH flags cleared (cascade works)")
        
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
        # Cleanup
        print(f"\n7. Cleanup: Deleting test user and data...")
        if conn:
            try:
                cleanup_test_user(conn, test_email)
            except Exception as ex:
                print(f"Warning: Cleanup failed: {ex}", file=sys.stderr)
                import traceback
                traceback.print_exc()
            finally:
                conn.close()


if __name__ == "__main__":
    sys.exit(main())
