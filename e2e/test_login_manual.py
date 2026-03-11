"""
Manual E2E test for login and refresh persistence.
Opens a browser, waits for you to manually log in, then tests refresh.
"""
import asyncio
import time
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://localhost:8000"


async def manual_test():
    print("\n" + "="*60)
    print("Manual Login + Refresh Test")
    print("="*60)
    print("\nThis test will:")
    print("1. Open a browser to the login page")
    print("2. Wait for YOU to manually log in")
    print("3. Verify tokens are stored")
    print("4. Refresh the page")
    print("5. Check if session persists")
    print("="*60 + "\n")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=500,
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
        )
        
        page = await context.new_page()
        
        # Navigate to login page
        print("Opening login page...")
        await page.goto(FRONTEND_URL, timeout=600000)  # 10 minute timeout
        # Don't wait for networkidle - Turnstile keeps connections open
        await page.wait_for_load_state('domcontentloaded', timeout=600000)
        
        # Wait for Turnstile to load
        print("Waiting for page to fully load (including Turnstile)...")
        await page.wait_for_timeout(10000)  # Wait 10 seconds for everything to load
        print("✓ Page loaded")
        
        print("\n" + "="*60)
        print("✋ PLEASE LOG IN NOW")
        print("="*60)
        print("Complete the login process in the browser.")
        print("After you're redirected to /resume, come back here.")
        print("="*60 + "\n")
        
        # Wait for user to log in (wait for /resume URL)
        input("Press ENTER after you've successfully logged in and are on the /resume page...")
        
        # Check current URL
        current_url = page.url
        print(f"\nCurrent URL: {current_url}")
        
        if not current_url.startswith(f"{FRONTEND_URL}/resume"):
            print(f"❌ ERROR: Not on /resume page. Current URL: {current_url}")
            print("Please navigate to /resume after login and try again.")
            await browser.close()
            return
        
        print("✓ On /resume page")
        
        # Check localStorage for tokens
        print("\n" + "="*60)
        print("Checking localStorage for tokens...")
        print("="*60)
        
        storage_state = await page.evaluate("""() => {
            const persistent = localStorage.getItem('__rt_access_token');
            const ephemeral = localStorage.getItem('__rt_ephemeral_token');
            const authExpect = localStorage.getItem('__rt_auth_expect_true');
            
            let persistentToken = null;
            let ephemeralToken = null;
            
            try {
                if (persistent) {
                    const obj = JSON.parse(persistent);
                    persistentToken = obj.t ? obj.t.substring(0, 30) + '...' : null;
                }
            } catch {}
            
            try {
                if (ephemeral) {
                    const obj = JSON.parse(ephemeral);
                    const expired = obj.e && Date.now() >= obj.e;
                    ephemeralToken = obj.t && !expired ? obj.t.substring(0, 30) + '...' : 'EXPIRED';
                }
            } catch {}
            
            return {
                hasPersistent: !!persistentToken,
                hasEphemeral: !!ephemeralToken && ephemeralToken !== 'EXPIRED',
                persistentPreview: persistentToken,
                ephemeralPreview: ephemeralToken,
                authExpectFlag: authExpect
            };
        }""")
        
        print(f"\n📦 localStorage state:")
        print(f"  - Persistent token: {'✓ PRESENT' if storage_state['hasPersistent'] else '✗ MISSING'}")
        if storage_state['persistentPreview']:
            print(f"    Preview: {storage_state['persistentPreview']}")
        print(f"  - Ephemeral token: {'✓ PRESENT' if storage_state['hasEphemeral'] else '✗ MISSING/EXPIRED'}")
        if storage_state['ephemeralPreview']:
            print(f"    Preview: {storage_state['ephemeralPreview']}")
        print(f"  - Auth expect flag: {storage_state['authExpectFlag']}")
        
        if not storage_state['hasPersistent']:
            print("\n❌ ERROR: No persistent token found!")
            print("Login may not have stored the token correctly.")
            await browser.close()
            return
        
        print("\n✓ Token storage looks good!")
        
        # Now test refresh
        print("\n" + "="*60)
        print("Testing page refresh...")
        print("="*60)
        
        print("\nRefreshing page...")
        await page.reload(wait_until='networkidle')
        print("✓ Page refreshed")
        
        # Wait a moment for any auth checks
        await page.wait_for_timeout(2000)
        
        # Check URL after refresh
        url_after_refresh = page.url
        print(f"\nURL after refresh: {url_after_refresh}")
        
        # Check storage again
        storage_after_refresh = await page.evaluate("""() => {
            const persistent = localStorage.getItem('__rt_access_token');
            return {
                hasPersistent: !!persistent
            };
        }""")
        
        print(f"Persistent token after refresh: {'✓ STILL PRESENT' if storage_after_refresh['hasPersistent'] else '✗ CLEARED'}")
        
        # Final verdict
        print("\n" + "="*60)
        print("TEST RESULT")
        print("="*60)
        
        if url_after_refresh.startswith(f"{FRONTEND_URL}/resume"):
            print("\n✅ SUCCESS!")
            print("   - Still on /resume page after refresh")
            print("   - Session persisted correctly")
            print("\nThe login + refresh flow is working! 🎉")
        elif url_after_refresh == FRONTEND_URL + "/" or url_after_refresh == FRONTEND_URL:
            print("\n❌ FAILED!")
            print("   - Redirected to login page after refresh")
            print("   - Session was lost")
            print("\nThe session is NOT persisting across refresh.")
            
            # Additional debugging
            print("\nDEBUGGING INFO:")
            print("1. Check if backend token has expired (default: 60 minutes)")
            print("2. Check browser DevTools > Application > Local Storage")
            print("3. Check browser DevTools > Network > look for /users/me request")
            print("4. Check if Authorization header is being sent with bearer token")
        else:
            print(f"\n⚠️  UNEXPECTED")
            print(f"   - Redirected to: {url_after_refresh}")
            print(f"   - Expected to stay on /resume")
        
        print("="*60 + "\n")
        
        # Keep browser open for inspection
        print("\n⏸️  Browser will remain open for 30 seconds for inspection...")
        print("Check the browser state, localStorage, Network tab, etc.")
        await page.wait_for_timeout(30000)
        
        await browser.close()
        print("\n✓ Test complete!")


if __name__ == "__main__":
    print("\n🔧 Manual Login + Refresh Persistence Test")
    print("==========================================")
    print("\nPrerequisites:")
    print("- Frontend running at http://localhost:3000")
    print("- Backend running at http://localhost:8000")
    print("- You have valid login credentials")
    print("- You can complete CAPTCHA manually")
    print("\nStarting test...\n")
    
    asyncio.run(manual_test())
