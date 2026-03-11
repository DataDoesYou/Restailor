"""
Manual test script for sidebar hydration and save functionality.
Run this directly with: poetry run python e2e/test_sidebar_manual.py
"""

import json
import os
import sys
import time
from playwright.sync_api import sync_playwright, Page, ConsoleMessage

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2


def get_db_connection():
    """Get database connection."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set - run with doppler")
    return psycopg2.connect(db_url)


def clear_user_preferences(user_id: int):
    """Clear user preferences."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_preferences WHERE user_id = %s", (user_id,))
            conn.commit()
            print(f"✓ Cleared preferences for user {user_id}")
    finally:
        conn.close()


def get_user_preferences(user_id: int):
    """Get user preferences."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT settings, version FROM user_preferences WHERE user_id = %s",
                (user_id,)
            )
            row = cur.fetchone()
            if row:
                return {"settings": row[0], "version": row[1]}
            return None
    finally:
        conn.close()


class TestResults:
    """Track test results."""
    
    def __init__(self):
        self.passed = []
        self.failed = []
        self.console_logs = []
    
    def log_console(self, msg: ConsoleMessage):
        """Log console message."""
        text = msg.text
        self.console_logs.append(text)
        if any(prefix in text for prefix in ["[SidebarModels]", "[useModelSettings]", "[apiClient]"]):
            print(f"  📝 {text}")
    
    def pass_test(self, name: str):
        """Mark test as passed."""
        self.passed.append(name)
        print(f"✅ PASS: {name}")
    
    def fail_test(self, name: str, reason: str):
        """Mark test as failed."""
        self.failed.append((name, reason))
        print(f"❌ FAIL: {name}")
        print(f"   Reason: {reason}")
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print(f"TEST SUMMARY: {len(self.passed)} passed, {len(self.failed)} failed")
        print("="*60)
        if self.passed:
            print("\n✅ Passed tests:")
            for test in self.passed:
                print(f"  - {test}")
        if self.failed:
            print("\n❌ Failed tests:")
            for test, reason in self.failed:
                print(f"  - {test}")
                print(f"    {reason}")
        print("="*60 + "\n")


def run_tests():
    """Run all tests."""
    results = TestResults()
    user_id = 1  # Test with user 1
    
    print("\n🧪 Starting Sidebar Hydration & Save Tests\n")
    print("="*60)
    
    # Clear preferences before starting
    try:
        clear_user_preferences(user_id)
    except Exception as e:
        print(f"⚠️  Warning: Could not clear preferences: {e}")
    
    with sync_playwright() as p:
        # Launch browser
        print("\n🌐 Launching browser...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Setup console logging
        page.on("console", results.log_console)
        
        # TEST 1: Page loads without errors
        print("\n📍 Test 1: Page loads successfully")
        try:
            page.goto("http://localhost:3000/", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=30000)
            results.pass_test("Page loads successfully")
        except Exception as e:
            results.fail_test("Page loads successfully", str(e))
            results.print_summary()
            browser.close()
            return
        
        # Wait for React hydration
        time.sleep(3)
        
        # TEST 2: Hydration completes
        print("\n📍 Test 2: Hydration completes")
        hydration_logs = [log for log in results.console_logs if "Initial hydration complete" in log]
        if hydration_logs:
            results.pass_test("Hydration completes")
            print(f"   Found: {hydration_logs[0]}")
        else:
            results.fail_test("Hydration completes", "No hydration complete log found")
            print("   Console logs containing [SidebarModels]:")
            sidebar_logs = [log for log in results.console_logs if "[SidebarModels]" in log]
            for log in sidebar_logs:
                print(f"     {log}")
        
        # TEST 3: Find multi-model checkbox
        print("\n📍 Test 3: Find multi-model checkbox")
        try:
            # Try multiple selectors
            checkbox = None
            selectors = [
                'input[type="checkbox"][data-testid*="multi"]',
                'label:has-text("Multi-model") input[type="checkbox"]',
                'label:has-text("multi") input[type="checkbox"]',
            ]
            
            for selector in selectors:
                try:
                    checkbox = page.locator(selector).first
                    if checkbox.count() > 0:
                        print(f"   Found checkbox with selector: {selector}")
                        break
                except:
                    continue
            
            if not checkbox or checkbox.count() == 0:
                # Fallback: find all checkboxes and print them
                all_checkboxes = page.locator('input[type="checkbox"]').all()
                print(f"   Found {len(all_checkboxes)} total checkboxes")
                
                # Get sidebar element
                sidebar = page.locator('[class*="sidebar"]').first
                if sidebar.count() > 0:
                    sidebar_checkboxes = sidebar.locator('input[type="checkbox"]').all()
                    print(f"   Found {len(sidebar_checkboxes)} checkboxes in sidebar")
                    if sidebar_checkboxes:
                        checkbox = sidebar.locator('input[type="checkbox"]').first
                
            if checkbox and checkbox.count() > 0:
                results.pass_test("Find multi-model checkbox")
            else:
                results.fail_test("Find multi-model checkbox", "Checkbox not found")
                results.print_summary()
                browser.close()
                return
                
        except Exception as e:
            results.fail_test("Find multi-model checkbox", str(e))
            results.print_summary()
            browser.close()
            return
        
        # TEST 4: Toggle checkbox triggers save
        print("\n📍 Test 4: Toggle checkbox triggers save")
        try:
            # Clear console logs
            results.console_logs.clear()
            
            # Get initial state
            is_checked = checkbox.is_checked()
            print(f"   Initial state: {'checked' if is_checked else 'unchecked'}")
            
            # Click checkbox
            checkbox.click()
            print("   Clicked checkbox")
            
            # Wait for save
            time.sleep(3)
            
            # Check for save logs
            save_triggered = any("Save effect triggered" in log for log in results.console_logs)
            api_called = any("[apiClient]" in log or "PUT" in log for log in results.console_logs)
            save_succeeded = any("Save succeeded" in log for log in results.console_logs)
            
            if save_triggered and api_called and save_succeeded:
                results.pass_test("Toggle triggers save flow")
            else:
                reason = []
                if not save_triggered:
                    reason.append("Save effect not triggered")
                if not api_called:
                    reason.append("API not called")
                if not save_succeeded:
                    reason.append("Save did not succeed")
                results.fail_test("Toggle triggers save flow", ", ".join(reason))
                print("   Recent console logs:")
                for log in results.console_logs[-10:]:
                    print(f"     {log}")
                
        except Exception as e:
            results.fail_test("Toggle triggers save flow", str(e))
        
        # TEST 5: Database updated
        print("\n📍 Test 5: Database is updated")
        try:
            prefs = get_user_preferences(user_id)
            if prefs:
                print(f"   Settings: {json.dumps(prefs['settings'], indent=2)}")
                print(f"   Version: {prefs['version']}")
                
                if "multi_model_enabled" in prefs["settings"]:
                    results.pass_test("Database updated with settings")
                else:
                    results.fail_test("Database updated with settings", 
                                    "multi_model_enabled not in settings")
            else:
                results.fail_test("Database updated with settings", 
                                "No preferences found in database")
        except Exception as e:
            results.fail_test("Database updated with settings", str(e))
        
        # TEST 6: State persists after refresh
        print("\n📍 Test 6: State persists after refresh")
        try:
            # Make sure checkbox is checked
            if not checkbox.is_checked():
                checkbox.click()
                time.sleep(2)
            
            expected_checked = checkbox.is_checked()
            print(f"   State before refresh: {'checked' if expected_checked else 'unchecked'}")
            
            # Refresh page
            results.console_logs.clear()
            page.reload()
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(3)
            
            # Find checkbox again
            checkbox = page.locator('input[type="checkbox"]').first
            actual_checked = checkbox.is_checked()
            print(f"   State after refresh: {'checked' if actual_checked else 'unchecked'}")
            
            if expected_checked == actual_checked:
                results.pass_test("State persists after refresh")
            else:
                results.fail_test("State persists after refresh",
                                f"Expected {expected_checked}, got {actual_checked}")
            
            # Check that settings were loaded from API
            get_logs = [log for log in results.console_logs if "GET" in log and "model-settings" in log]
            if get_logs:
                print(f"   Loaded from API: {get_logs[0]}")
            
        except Exception as e:
            results.fail_test("State persists after refresh", str(e))
        
        # Cleanup
        print("\n🧹 Cleaning up...")
        browser.close()
    
    # Print final summary
    results.print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if not results.failed else 1)


if __name__ == "__main__":
    try:
        run_tests()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Test crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
