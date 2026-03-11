#!/usr/bin/env python
"""
🔒 NAVIGATION BLOCKING E2E TEST
Test that user CANNOT navigate during Applied checkbox mutation

PROBLEM:
User clicks Applied checkbox → clicks History immediately → sees stale data

SOLUTION:
Set __rt_mutation_in_progress flag SYNCHRONOUSLY → blocks navigation

TEST APPROACH:
1. Use Playwright to control actual browser
2. Click Applied checkbox
3. IMMEDIATELY try to click History link (< 1ms)
4. Verify:
   - History link click was BLOCKED
   - User stays on Resume Tailor page
   - After mutation completes, navigation works again
"""

import sys
import os
import time
import random
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright, expect
import psycopg2
import requests


def test_navigation_blocking():
    """Test that navigation is blocked during Applied checkbox mutation"""
    print("=" * 70)
    print("🔒 NAVIGATION BLOCKING TEST")
    print("=" * 70)
    print()
    
    # Connect to database
    print("📊 Connecting to database...")
    db_host = os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST", "localhost")
    if db_host == "postgres":
        db_host = "localhost"
    
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME") or os.getenv("POSTGRES_DB", "rt"),
        user=os.getenv("DB_USER") or os.getenv("POSTGRES_USER", "rt_user"),
        password=os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD", "secret"),
        host=db_host,
        port=int(os.getenv("DB_PORT") or os.getenv("POSTGRES_PORT", "5432"))
    )
    conn.autocommit = True
    cursor = conn.cursor()
    print("✓ Database connected\n")
    
    # Create test user
    print("1️⃣  Creating test user...")
    test_email = f"navblock_test_{int(time.time())}@example.com"
    test_password = "TestPassword123!"
    
    backend_url = "http://localhost:8000"
    
    # Register user
    reg_resp = requests.post(f"{backend_url}/auth/register", json={
        "email": test_email,
        "password": test_password
    })
    if not reg_resp.ok or not reg_resp.json().get("ok"):
        raise Exception(f"Failed to register: {reg_resp.text}")
    
    # Verify email
    cursor.execute("SELECT id FROM rt_user WHERE email = %s", (test_email,))
    user_row = cursor.fetchone()
    if not user_row:
        raise Exception("User not created")
    user_id = user_row[0]
    
    cursor.execute("UPDATE rt_user SET email_verified = TRUE WHERE id = %s", (user_id,))
    print(f"✓ User created and verified (ID={user_id})\n")
    
    # Login
    print("2️⃣  Logging in...")
    login_resp = requests.post(f"{backend_url}/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    if not login_resp.ok or not login_resp.json().get("ok"):
        raise Exception(f"Failed to login: {login_resp.text}")
    
    session_token = login_resp.json().get("sessionToken")
    if not session_token:
        raise Exception("No session token returned")
    
    print("✓ Logged in\n")
    
    # Start Playwright
    print("3️⃣  Starting browser test...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        
        # Set session cookie
        context.add_cookies([{
            "name": "rt_session",
            "value": session_token,
            "domain": "localhost",
            "path": "/",
            "httpOnly": True,
            "secure": False,
            "sameSite": "Lax"
        }])
        
        page = context.new_page()
        
        # Navigate to Resume Tailor page
        page.goto("http://localhost:3000/resume")
        page.wait_for_load_state("networkidle")
        
        # Fill in some content
        print("   📝 Filling in resume and job description...")
        resume_input = page.locator('textarea[placeholder*="resume" i]').first
        jd_input = page.locator('textarea[placeholder*="job" i]').first
        
        resume_input.fill("Test Resume Content\nSoftware Engineer")
        jd_input.fill("Test Job Description\nWe need a software engineer")
        
        # Wait a moment for content to be set
        time.sleep(0.5)
        
        # Find the Applied checkbox
        print("   🔲 Finding Applied checkbox...")
        applied_checkbox = page.get_by_role("checkbox", name="Applied")
        
        # Ensure checkbox is visible and unchecked
        expect(applied_checkbox).to_be_visible()
        if applied_checkbox.is_checked():
            print("   ⚠️  Checkbox already checked, unchecking first...")
            applied_checkbox.click()
            page.wait_for_timeout(100)
        
        # Find History link
        print("   🔗 Finding History link...")
        history_link = page.get_by_role("link", name="History")
        expect(history_link).to_be_visible()
        
        # Get current URL
        initial_url = page.url
        print(f"   📍 Current URL: {initial_url}")
        
        # TEST 1: Click checkbox and IMMEDIATELY try to navigate
        print("\n   ⚡ TEST: Click Applied → INSTANT History click")
        print("   " + "-" * 60)
        
        # Click Applied checkbox (starts mutation)
        applied_checkbox.click()
        
        # IMMEDIATELY try to click History (< 1ms)
        # If navigation blocking works, this click will be intercepted
        history_link.click()
        
        # Wait a tiny bit to see if navigation happened
        page.wait_for_timeout(50)
        
        # Check if we're still on Resume Tailor page
        current_url = page.url
        print(f"   📍 After instant click: {current_url}")
        
        if "resume" in current_url.lower():
            print("   ✅ BLOCKED: Still on Resume Tailor page (navigation prevented!)")
            blocked = True
        else:
            print(f"   ❌ NOT BLOCKED: Navigated to {current_url}")
            blocked = False
        
        # Wait for mutation to complete (check for unlock message in console)
        print("\n   ⏱️  Waiting for mutation to complete...")
        page.wait_for_timeout(200)
        
        # Check database to verify update completed
        cursor.execute("""
            SELECT is_applied 
            FROM rt_application_jd 
            WHERE user_id = %s 
            ORDER BY updated_at DESC 
            LIMIT 1
        """, (user_id,))
        db_row = cursor.fetchone()
        db_is_applied = db_row[0] if db_row else False
        
        print(f"   📊 Database state after mutation: is_applied={db_is_applied}")
        
        if db_is_applied:
            print("   ✅ Database updated successfully")
        else:
            print("   ⚠️  Database NOT updated (mutation may have failed)")
        
        # TEST 2: Now try to navigate again (should work after unlock)
        print("\n   ⚡ TEST: Navigation after mutation completes")
        print("   " + "-" * 60)
        
        # Go back to Resume Tailor if we somehow left
        if "resume" not in page.url.lower():
            page.goto("http://localhost:3000/resume")
            page.wait_for_load_state("networkidle")
        
        # Try to navigate to History again
        history_link = page.get_by_role("link", name="History")
        history_link.click()
        
        # Wait for navigation
        page.wait_for_timeout(500)
        
        current_url = page.url
        print(f"   📍 After delayed click: {current_url}")
        
        if "history" in current_url.lower():
            print("   ✅ ALLOWED: Successfully navigated to History")
            allowed_after = True
        else:
            print("   ❌ BLOCKED: Still on Resume Tailor (should be allowed now!)")
            allowed_after = False
        
        browser.close()
    
    # Clean up test user
    print("\n4️⃣  Cleaning up...")
    cursor.execute("DELETE FROM rt_user WHERE email = %s", (test_email,))
    print(f"✓ Cleaned up test user: {test_email}")
    
    cursor.close()
    conn.close()
    
    # Evaluate test results
    print("\n" + "=" * 70)
    print("📊 TEST RESULTS")
    print("=" * 70)
    
    all_passed = True
    
    if blocked:
        print("✅ TEST 1 PASSED: Navigation blocked during mutation")
    else:
        print("❌ TEST 1 FAILED: Navigation NOT blocked during mutation")
        all_passed = False
    
    if db_is_applied:
        print("✅ TEST 2 PASSED: Database updated successfully")
    else:
        print("❌ TEST 2 FAILED: Database NOT updated")
        all_passed = False
    
    if allowed_after:
        print("✅ TEST 3 PASSED: Navigation allowed after mutation completes")
    else:
        print("❌ TEST 3 FAILED: Navigation still blocked after mutation")
        all_passed = False
    
    print("=" * 70)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED - Navigation blocking works correctly!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED - Navigation blocking not working properly")
        return 1


if __name__ == "__main__":
    try:
        exit_code = test_navigation_blocking()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
