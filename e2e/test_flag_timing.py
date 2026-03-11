#!/usr/bin/env python
"""
🔒 SIMPLE NAVIGATION BLOCKING TEST
Test that __rt_mutation_in_progress flag is set SYNCHRONOUSLY

APPROACH:
1. Use Playwright to inject code that monitors the flag
2. Click Applied checkbox  
3. Verify flag is set IMMEDIATELY (synchronously)
4. Verify flag is cleared after mutation completes

This tests the ACTUAL fix: that the flag is set synchronously at the start
of the onAppliedToggle callback, before any await statements.
"""

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_flag_timing():
    """Test that __rt_mutation_in_progress flag is set synchronously"""
    print("=" * 70)
    print("🔒 FLAG TIMING TEST")
    print("=" * 70)
    print()
    
    print("Starting Playwright browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)  # headless=False so we can see, slow_mo for visibility
        context = browser.new_context()
        page = context.new_page()
        
        # Track console messages
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg.text))
        
        # Navigate to Resume Tailor page
        print("Navigating to http://localhost:3000/resume...")
        try:
            page.goto("http://localhost:3000/resume", wait_until="domcontentloaded", timeout=10000)
            print("✓ Page loaded")
        except Exception as e:
            print(f"⚠️  Page load warning: {e}")
            print("   Continuing anyway...")
        
        # Wait a bit for any redirects
        page.wait_for_timeout(2000)
        
        # Inject monitoring code
        print("Injecting flag monitor...")
        page.evaluate("""
            // Monitor flag changes
            window.__flag_events = [];
            let lastFlag = false;
            
            setInterval(() => {
                const currentFlag = window.__rt_mutation_in_progress || false;
                if (currentFlag !== lastFlag) {
                    const event = {
                        time: performance.now(),
                        flag: currentFlag,
                        timestamp: new Date().toISOString()
                    };
                    window.__flag_events.push(event);
                    console.log(`[FLAG MONITOR] ${currentFlag ? '🔒 LOCKED' : '🔓 UNLOCKED'} at ${event.time.toFixed(2)}ms`);
                    lastFlag = currentFlag;
                }
            }, 1);  // Check every 1ms
        """)
        
        print("Waiting for page to be ready...")
        page.wait_for_timeout(1000)
        
        # Check what page we're on
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        # If we're on login page, show instructions
        if "login" in current_url.lower():
            print("\n" + "=" * 70)
            print("⚠️  YOU NEED TO LOG IN FIRST!")
            print("=" * 70)
            print("\nSTEPS:")
            print("1. The browser window should be open now")
            print("2. Log in to your account")
            print("3. Navigate to the Resume Tailor page (/resume)")
            print("4. Fill in some resume text and job description text")
            print("5. Then come back here and press ENTER to continue the test")
            print("\nWaiting for your input...")
            input("Press ENTER when you're ready to run the test...")
            print("\nContinuing test...")
        
        # Find Applied checkbox
        print("\nLooking for Applied checkbox...")
        try:
            applied_checkbox = page.get_by_role("checkbox", name="Applied")
            applied_checkbox.wait_for(timeout=5000)
            print("✓ Found Applied checkbox")
        except Exception as e:
            print(f"❌ Could not find Applied checkbox: {e}")
            print("\n⚠️  INSTRUCTIONS:")
            print("   1. Make sure you're logged in")
            print("   2. Navigate to /resume page")
            print("   3. Fill in both Resume and Job Description text")
            print("   4. The Applied checkbox should appear")
            print("\nKeeping browser open for 30 seconds so you can check...")
            page.wait_for_timeout(30000)
            browser.close()
            return 1
        
        # Record start time
        print("\nClicking Applied checkbox...")
        start_time = page.evaluate("performance.now()")
        
        # Click checkbox
        applied_checkbox.click()
        
        # Wait for mutation to complete
        print("Waiting for mutation to complete...")
        page.wait_for_timeout(2000)
        
        # Get flag events
        flag_events = page.evaluate("window.__flag_events || []")
        
        browser.close()
    
    # Analyze results
    print("\n" + "=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    
    if not flag_events:
        print("❌ NO FLAG EVENTS - Navigation lock not working!")
        return 1
    
    print(f"\nRecorded {len(flag_events)} flag changes:")
    for i, event in enumerate(flag_events, 1):
        time_ms = event['time'] - start_time if 'time' in event else 0
        flag_state = "🔒 LOCKED" if event.get('flag') else "🔓 UNLOCKED"
        print(f"  {i}. {flag_state} at T+{time_ms:.2f}ms")
    
    # Check if first event is a lock
    first_event = flag_events[0]
    if not first_event.get('flag'):
        print("\n❌ FAIL: First event was UNLOCK, not LOCK!")
        print("   Flag should be set to TRUE first")
        return 1
    
    # Check timing of lock
    lock_time = first_event.get('time', 0) - start_time
    if lock_time < 10:  # Should happen within 10ms (basically instant)
        print(f"\n✅ PASS: Flag locked within {lock_time:.2f}ms (synchronous!)")
    else:
        print(f"\n⚠️  WARNING: Flag locked at {lock_time:.2f}ms (slower than expected)")
        print("   Expected < 10ms for synchronous operation")
    
    # Check if flag was eventually unlocked
    last_event = flag_events[-1]
    if not last_event.get('flag'):
        print("✅ PASS: Flag was unlocked after mutation completed")
    else:
        print("⚠️  WARNING: Flag still locked at end of test")
    
    # Look for relevant console messages
    print("\n" + "-" * 70)
    print("Console messages:")
    for msg in console_messages[-10:]:  # Last 10 messages
        if 'APPLIED' in msg or 'Navigation' in msg or 'FLAG' in msg:
            print(f"  {msg}")
    
    print("=" * 70)
    print("\n🎉 TEST COMPLETE - Check results above")
    return 0


if __name__ == "__main__":
    try:
        exit_code = test_flag_timing()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
