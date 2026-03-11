"""
Standalone test for model selection events - no pytest dependency.
Run with: poetry run python tests/test_model_selection_standalone.py
"""

from playwright.sync_api import sync_playwright
import sys


def test_model_selection():
    print("\n=== Testing Model Selection Events ===\n")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # Navigate to resume page with debug
            print("1. Navigating to http://localhost:3000/resume?rt_debug=1...")
            try:
                page.goto("http://localhost:3000/resume?rt_debug=1", timeout=10000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"   ✗ Failed to load page: {e}")
                print(f"   Make sure dev server is running: npm run dev")
                return False
            
            print("   ✓ Page loaded\n")
            
            # Set up event listener
            print("2. Setting up event listeners...")
            page.evaluate("""
                window.__test_rt_sidebar_events = [];
                window.__test_rt_multi_events = [];
                
                window.addEventListener('rt-sidebar', (e) => {
                    console.log('[TEST] rt-sidebar received:', e.detail);
                    window.__test_rt_sidebar_events.push(e.detail || {});
                });
                
                window.addEventListener('rt-multi-models', (e) => {
                    console.log('[TEST] rt-multi-models received:', e.detail);
                    window.__test_rt_multi_events.push(e.detail || {});
                });
            """)
            print("   ✓ Event listeners installed\n")
            
            # Wait a moment for any initial events
            page.wait_for_timeout(1000)
            
            # Check if any events were dispatched on page load
            initial_sidebar_events = page.evaluate("window.__test_rt_sidebar_events.length")
            initial_multi_events = page.evaluate("window.__test_rt_multi_events.length")
            
            print(f"3. Initial events: {initial_sidebar_events} rt-sidebar, {initial_multi_events} rt-multi-models")
            
            if initial_sidebar_events > 0:
                latest_event = page.evaluate("window.__test_rt_sidebar_events[window.__test_rt_sidebar_events.length - 1]")
                fit_label = latest_event.get('fitModelLabel', '')
                print(f"   Latest fitModelLabel: {fit_label}")
                
                if fit_label:
                    if ' — ' in fit_label and '(' in fit_label:
                        print(f"   ✓ Label has correct format (em-dash and description)")
                    else:
                        print(f"   ✗ Label format incorrect: missing em-dash or description")
                        print(f"     Expected format: 'Alias — Provider (description)'")
                        print(f"     Got: '{fit_label}'")
                        return False
                else:
                    print(f"   ⚠ fitModelLabel is empty")
            
            print("\n4. Testing validation error message...")
            
            # Fill in text areas
            page.locator("textarea").first.fill("Test resume content")
            page.locator("textarea").nth(1).fill("Test job description")
            print("   ✓ Filled resume and JD fields")
            
            # Click Check Fit
            check_fit_btn = page.locator("button").filter(has_text="Check Fit").or_(
                page.locator("button").filter(has_text="check fit")
            ).first
            check_fit_btn.click()
            print("   ✓ Clicked Check Fit button")
            
            # Wait for error or success
            page.wait_for_timeout(2000)
            
            # Look for validation error
            error_locator = page.locator("text=/please select.*fit.*model/i").first
            
            if error_locator.is_visible(timeout=1000):
                error_text = error_locator.text_content() or ""
                print(f"\n   Validation error appeared:")
                print(f"   {error_text}\n")
                
                # Check debug info format
                if '(label=' in error_text:
                    import re
                    match = re.search(r'\(label=([^,]+),\s*meta=([^,]+),\s*multi=([^)]+)\)', error_text)
                    
                    if match:
                        label_val = match.group(1).strip()
                        meta_val = match.group(2).strip()
                        multi_val = match.group(3).strip()
                        
                        print(f"   Debug info parsed:")
                        print(f"     label: {label_val}")
                        print(f"     meta:  {meta_val}")
                        print(f"     multi: {multi_val}\n")
                        
                        # Check if it's NULL (no model selected) or has value
                        if label_val == 'NULL':
                            print(f"   ⚠ Label is NULL - no model selected")
                            print(f"   This is expected if no model was selected in sidebar")
                        else:
                            print(f"   ✓ Label has value: {label_val}")
                            
                            # Verify format
                            if ' — ' in label_val:
                                print(f"   ✓ Label contains em-dash separator")
                            else:
                                print(f"   ✗ Label missing em-dash - got alias instead of full label!")
                                return False
                        
                        if multi_val in ['YES', 'NO']:
                            print(f"   ✓ Multi-mode value is valid: {multi_val}")
                        else:
                            print(f"   ✗ Invalid multi-mode value: {multi_val}")
                            return False
                        
                        print(f"\n   ✓ Debug info format is correct")
                        return True
                    else:
                        print(f"   ✗ Could not parse debug info from error")
                        return False
                else:
                    print(f"   ✗ Error message missing debug info")
                    return False
            else:
                print(f"\n   ✓ No validation error - model is properly selected and validation passed")
                return True
                
        except Exception as e:
            print(f"\n   ✗ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            browser.close()


if __name__ == "__main__":
    success = test_model_selection()
    print("\n" + "="*50)
    if success:
        print("TEST PASSED ✓")
        sys.exit(0)
    else:
        print("TEST FAILED ✗")
        sys.exit(1)
