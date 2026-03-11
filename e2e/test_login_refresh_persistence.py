"""
E2E test for login flow and session persistence across page refresh.
Tests the complete authentication flow including bearer tokens and cookies.
"""
import asyncio
import json
import os
import time
from playwright.async_api import async_playwright, Page, BrowserContext, expect

# Test credentials - update these with valid test user
TEST_EMAIL = os.getenv("TEST_EMAIL", "test@example.com")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "testpassword123")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


async def debug_storage_and_cookies(page: Page, label: str):
    """Debug helper to inspect localStorage, sessionStorage, and cookies"""
    print(f"\n{'='*60}")
    print(f"[{label}] Storage and Cookie State")
    print('='*60)
    
    # Check localStorage
    local_storage = await page.evaluate("""() => {
        const items = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key) {
                try {
                    items[key] = JSON.parse(localStorage.getItem(key));
                } catch {
                    items[key] = localStorage.getItem(key);
                }
            }
        }
        return items;
    }""")
    
    print(f"\n📦 localStorage ({len(local_storage)} items):")
    for key, value in local_storage.items():
        if 'token' in key.lower():
            if isinstance(value, dict) and 't' in value:
                token_preview = value['t'][:20] + '...' if len(value['t']) > 20 else value['t']
                print(f"  - {key}: {{ t: '{token_preview}', ... }}")
            else:
                print(f"  - {key}: {value}")
        else:
            print(f"  - {key}: {value}")
    
    # Check cookies
    cookies = await page.context.cookies()
    print(f"\n🍪 Cookies ({len(cookies)} total):")
    for cookie in cookies:
        if 'rt_' in cookie['name'] or 'session' in cookie['name'].lower():
            print(f"  - {cookie['name']}: {cookie['value'][:30]}... (domain: {cookie['domain']})")
    
    # Check if tokens are valid
    has_persistent = await page.evaluate("""() => {
        const raw = localStorage.getItem('__rt_access_token');
        if (!raw) return false;
        try {
            const obj = JSON.parse(raw);
            return !!(obj && obj.t);
        } catch { return false; }
    }""")
    
    has_ephemeral = await page.evaluate("""() => {
        const raw = localStorage.getItem('__rt_ephemeral_token');
        if (!raw) return false;
        try {
            const obj = JSON.parse(raw);
            const expired = obj.e && Date.now() >= obj.e;
            return !!(obj && obj.t && !expired);
        } catch { return false; }
    }""")
    
    print(f"\n✓ Token Status:")
    print(f"  - Persistent token: {'✓ PRESENT' if has_persistent else '✗ MISSING'}")
    print(f"  - Ephemeral token: {'✓ PRESENT (not expired)' if has_ephemeral else '✗ MISSING/EXPIRED'}")
    
    # Check auth flags
    auth_flags = await page.evaluate("""() => {
        return {
            __rt_was_logged_in: window.__rt_was_logged_in,
            __rt_auth_expect_true: localStorage.getItem('__rt_auth_expect_true'),
        };
    }""")
    print(f"\n🚩 Auth Flags:")
    print(f"  - __rt_was_logged_in: {auth_flags['__rt_was_logged_in']}")
    print(f"  - __rt_auth_expect_true: {auth_flags['__rt_auth_expect_true']}")
    
    print('='*60 + '\n')


async def test_login_and_refresh():
    """Test complete login flow and verify session persists after refresh"""
    
    print(f"\n{'='*60}")
    print("Starting Login + Refresh Persistence E2E Test")
    print('='*60)
    print(f"Frontend: {FRONTEND_URL}")
    print(f"Backend: {BACKEND_URL}")
    print(f"Test User: {TEST_EMAIL}")
    
    async with async_playwright() as p:
        # Launch browser with realistic settings
        browser = await p.chromium.launch(
            headless=False,  # Set to True for CI
            slow_mo=100,  # Slow down a bit for stability
            timeout=60000,  # Increase timeout to 60 seconds
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        )
        
        # Enable request/response logging
        context.on("request", lambda request: print(f"  → {request.method} {request.url}"))
        context.on("response", lambda response: print(f"  ← {response.status} {response.url}"))
        
        page = await context.new_page()
        
        # Listen for console logs
        page.on("console", lambda msg: print(f"  [Console {msg.type}] {msg.text}"))
        
        try:
            # ============================================================
            # STEP 1: Navigate to login page
            # ============================================================
            print(f"\n{'='*60}")
            print("STEP 1: Navigate to login page")
            print('='*60)
            
            await page.goto(FRONTEND_URL)
            await page.wait_for_load_state('networkidle')
            
            # Verify we're on login page
            await expect(page.get_by_text("Log in")).to_be_visible(timeout=10000)
            print("✓ Login page loaded")
            
            await debug_storage_and_cookies(page, "BEFORE LOGIN")
            
            # ============================================================
            # STEP 2: Fill credentials and submit
            # ============================================================
            print(f"\n{'='*60}")
            print("STEP 2: Submit login form")
            print('='*60)
            
            # Fill email
            email_input = page.locator('input[type="email"]')
            await email_input.fill(TEST_EMAIL)
            print(f"✓ Filled email: {TEST_EMAIL}")
            
            # Fill password
            password_input = page.locator('input[type="password"]')
            await password_input.fill(TEST_PASSWORD)
            print(f"✓ Filled password: {'*' * len(TEST_PASSWORD)}")
            
            # Click login button
            login_button = page.get_by_role("button", name="Log in")
            await login_button.click()
            print("✓ Clicked login button")
            
            # ============================================================
            # STEP 3: Wait for navigation to /resume
            # ============================================================
            print(f"\n{'='*60}")
            print("STEP 3: Wait for successful login and navigation")
            print('='*60)
            
            # Wait for navigation to /resume (indicates successful login)
            try:
                await page.wait_for_url(f"{FRONTEND_URL}/resume", timeout=15000)
                print(f"✓ Navigated to /resume")
            except Exception as e:
                print(f"✗ Failed to navigate to /resume: {e}")
                
                # Check for 2FA prompt
                if await page.get_by_text("Two-Factor Authentication").is_visible():
                    print("\n⚠️  2FA is enabled for this account!")
                    print("Please disable 2FA for the test account or update the test to handle it.")
                    raise Exception("2FA detected - test account should not have 2FA enabled")
                
                # Check for error messages
                error_alerts = page.locator('[role="alert"]')
                if await error_alerts.count() > 0:
                    error_text = await error_alerts.first.text_content()
                    print(f"✗ Error alert: {error_text}")
                
                raise
            
            # Wait for page to be fully loaded
            await page.wait_for_load_state('networkidle')
            
            await debug_storage_and_cookies(page, "AFTER LOGIN")
            
            # ============================================================
            # STEP 4: Verify user is logged in
            # ============================================================
            print(f"\n{'='*60}")
            print("STEP 4: Verify logged-in state")
            print('='*60)
            
            # Check for elements that only appear when logged in
            # (adjust selectors based on your actual UI)
            try:
                # Wait for a user-specific element (e.g., logout button, user menu, etc.)
                # Adjust this selector to match something that's definitely visible when logged in
                await page.wait_for_selector('text="Resume"', timeout=5000)
                print("✓ User-specific UI elements visible")
            except:
                print("⚠️  Could not verify user-specific UI elements")
            
            # Verify token is stored
            has_token = await page.evaluate("""() => {
                const token = localStorage.getItem('__rt_access_token');
                return !!token;
            }""")
            
            if has_token:
                print("✓ Access token stored in localStorage")
            else:
                print("✗ No access token in localStorage!")
                raise Exception("Access token not stored after login")
            
            # ============================================================
            # STEP 5: Perform page refresh
            # ============================================================
            print(f"\n{'='*60}")
            print("STEP 5: Refresh page to test session persistence")
            print('='*60)
            
            print("Refreshing page...")
            await page.reload(wait_until='networkidle')
            print("✓ Page refreshed")
            
            # Wait a moment for any auth checks to complete
            await page.wait_for_timeout(2000)
            
            await debug_storage_and_cookies(page, "AFTER REFRESH")
            
            # ============================================================
            # STEP 6: Verify still logged in after refresh
            # ============================================================
            print(f"\n{'='*60}")
            print("STEP 6: Verify session persisted after refresh")
            print('='*60)
            
            # Check current URL - should still be /resume, not redirected to /
            current_url = page.url
            print(f"Current URL: {current_url}")
            
            if current_url == FRONTEND_URL + "/" or current_url == FRONTEND_URL:
                print("✗ FAILED: Redirected to login page after refresh")
                print("Session was NOT persisted!")
                
                # Additional debugging
                print("\nChecking for auth errors in console...")
                
                raise Exception("Session not persisted - user was logged out after refresh")
            
            elif current_url.startswith(FRONTEND_URL + "/resume"):
                print("✓ SUCCESS: Still on /resume page")
                print("Session persisted correctly!")
            else:
                print(f"⚠️  Unexpected URL: {current_url}")
            
            # Verify token still exists
            has_token_after_refresh = await page.evaluate("""() => {
                const token = localStorage.getItem('__rt_access_token');
                return !!token;
            }""")
            
            if has_token_after_refresh:
                print("✓ Access token still in localStorage")
            else:
                print("✗ Access token was cleared!")
            
            # Try to make an authenticated API call
            print("\nTesting authenticated API call...")
            api_response = await page.evaluate(f"""async () => {{
                try {{
                    const res = await fetch('{BACKEND_URL}/users/me', {{
                        headers: {{
                            'Authorization': `Bearer ${{localStorage.getItem('__rt_access_token') ? JSON.parse(localStorage.getItem('__rt_access_token')).t : ''}}`,
                        }}
                    }});
                    return {{ status: res.status, ok: res.ok }};
                }} catch (e) {{
                    return {{ error: e.message }};
                }}
            }}""")
            
            print(f"API call result: {api_response}")
            
            if api_response.get('ok'):
                print("✓ Authenticated API call successful")
            else:
                print(f"✗ Authenticated API call failed: {api_response}")
            
            # ============================================================
            # FINAL RESULT
            # ============================================================
            print(f"\n{'='*60}")
            print("TEST RESULT")
            print('='*60)
            
            if current_url.startswith(FRONTEND_URL + "/resume") and has_token_after_refresh:
                print("✅ TEST PASSED: Login and refresh persistence working correctly!")
            else:
                print("❌ TEST FAILED: Session was lost after page refresh")
            
            print('='*60 + '\n')
            
            # Keep browser open for manual inspection
            print("\n⏸️  Browser will remain open for 10 seconds for inspection...")
            await page.wait_for_timeout(10000)
            
        except Exception as e:
            print(f"\n❌ TEST FAILED WITH ERROR:")
            print(f"{type(e).__name__}: {e}")
            
            # Take screenshot on failure
            screenshot_path = "test_login_refresh_failure.png"
            await page.screenshot(path=screenshot_path)
            print(f"\n📸 Screenshot saved to: {screenshot_path}")
            
            # Keep browser open longer on failure
            print("\n⏸️  Browser will remain open for 30 seconds for debugging...")
            await page.wait_for_timeout(30000)
            
            raise
        
        finally:
            try:
                await browser.close()
            except Exception as close_error:
                print(f"\n⚠️  Error closing browser: {close_error}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Login + Refresh Persistence E2E Test")
    print("="*60)
    print("\nPrerequisites:")
    print("1. Frontend running at", FRONTEND_URL)
    print("2. Backend running at", BACKEND_URL)
    print("3. Test account exists with credentials:")
    print(f"   Email: {TEST_EMAIL}")
    print(f"   Password: {TEST_PASSWORD}")
    print("4. 2FA should be DISABLED for test account")
    print("\nSet env vars to customize:")
    print("  TEST_EMAIL, TEST_PASSWORD, FRONTEND_URL, BACKEND_URL")
    print("="*60 + "\n")
    
    asyncio.run(test_login_and_refresh())
