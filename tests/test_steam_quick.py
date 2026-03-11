#!/usr/bin/env python3
"""
Quick test to verify Steam-like behavior.
This simulates clicking Applied checkbox and immediately checking the database.
"""
import time
import requests
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = "http://localhost:8000"
def get_db_config():
    """Get database config from environment."""
    return {
        "host": os.getenv("DATABASE_HOST", "localhost"),
        "port": int(os.getenv("DATABASE_PORT", "5432")),
        "database": os.getenv("DATABASE_NAME", "restailor"),
        "user": os.getenv("DATABASE_USER", "postgres"),
        "password": os.getenv("DATABASE_PASSWORD", ""),
    }

def check_db_applied_count(user_id=4):
    """Check how many jobs are marked as applied in database."""
    conn = psycopg2.connect(**get_db_config())
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM applications WHERE user_id = %s AND is_applied = true",
        (user_id,)
    )
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count

def main():
    print("\n=== STEAM BEHAVIOR TEST ===\n")
    
    # Get auth token (assumes you're logged in)
    print("Step 1: Checking authentication...")
    try:
        # Try to get current session
        resp = requests.get(f"{BACKEND_URL}/auth/me", timeout=5)
        if resp.status_code == 401:
            print("❌ Not logged in. Please log in to the app first.")
            print("   Visit: http://localhost:3000/login")
            return 1
        
        user_data = resp.json()
        user_id = user_data.get("id")
        print(f"✓ Logged in as user {user_id}")
    except Exception as e:
        print(f"❌ Error checking auth: {e}")
        print("   Make sure backend is running: doppler run -- poetry run python main.py")
        return 1
    
    # Check initial database state
    print("\nStep 2: Checking initial database state...")
    initial_count = check_db_applied_count(user_id)
    print(f"✓ Database shows {initial_count} applied job(s)")
    
    # This test just shows you the current state
    # You'll need to test the actual checkbox behavior in the browser
    print("\n=== MANUAL TEST INSTRUCTIONS ===\n")
    print("1. Open: http://localhost:3000/resume")
    print("2. Open Browser Console (F12)")
    print("3. Click the 'I applied with this version' checkbox")
    print("4. Watch console for:")
    print("   - [APPLY] 🔒 Navigation blocked")
    print("   - [APPLY] 🔓 Navigation unlocked")
    print("5. IMMEDIATELY click 'History' link")
    print("6. Expected: Click is blocked OR navigation works but data is saved")
    print("\n7. Then run this script again to verify database:")
    print("   doppler run -- poetry run python test_steam_quick.py")
    
    print(f"\n✓ Current applied count: {initial_count}")
    print("  After toggling checkbox, count should change immediately!")
    
    return 0

if __name__ == "__main__":
    exit(main())
