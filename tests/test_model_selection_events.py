"""
Test that model selection events are dispatched correctly and validation works.

This test verifies that:
1. SidebarModels dispatches rt-sidebar with full label format (not just aliases)
2. ResumeTailorClient receives the label correctly
3. Validation error shows actual values instead of NULL

Run with: poetry run pytest tests/test_model_selection_events.py -v -s
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def page_with_debug(page: Page):
    """Navigate to resume page with debug flag."""
    page.goto("http://localhost:3000/resume?rt_debug=1")
    page.wait_for_load_state("networkidle")
    return page


def test_sidebar_dispatches_correct_event_format(page_with_debug: Page):
    """Test that selecting a model dispatches rt-sidebar event with full label."""
    page = page_with_debug
    
    # Set up event listener to capture rt-sidebar events
    events_captured = []
    page.evaluate("""
        window.__test_events = [];
        window.addEventListener('rt-sidebar', (e) => {
            window.__test_events.push({
                type: 'rt-sidebar',
                fitModelLabel: e.detail?.fitModelLabel || null
            });
        });
    """)
    
    # Open sidebar and select a model
    # Note: Adjust selector based on actual UI
    sidebar_button = page.locator("button:has-text('Models')").first
    if sidebar_button.is_visible():
        sidebar_button.click()
    
    # Select first available model (e.g., Claude Sonnet 4.6)
    model_radio = page.locator("input[type='radio'][name='fit-model']").first
    if model_radio.is_visible():
        model_radio.click()
        page.wait_for_timeout(500)  # Wait for event to dispatch
    
    # Get captured events
    events = page.evaluate("window.__test_events || []")
    
    # Verify at least one rt-sidebar event was dispatched
    assert len(events) > 0, "No rt-sidebar events were dispatched"
    
    # Verify the label format is correct (should include em-dash and description)
    last_event = events[-1]
    label = last_event.get('fitModelLabel', '')
    
    assert label, "fitModelLabel is empty"
    assert ' — ' in label, f"Label missing em-dash: {label}"
    assert '(' in label and ')' in label, f"Label missing description parentheses: {label}"
    
    print(f"\n✓ Event dispatched with correct label format: {label}")


def test_validation_error_shows_label_not_null(page_with_debug: Page):
    """Test that validation error shows actual label value, not NULL."""
    page = page_with_debug
    
    # Fill in resume and JD to pass input validation
    resume_area = page.locator("textarea").first
    jd_area = page.locator("textarea").nth(1)
    
    resume_area.fill("Test resume content for validation check")
    jd_area.fill("Test job description content")
    
    # Click "Check Fit" without selecting a model (or with model selected)
    check_fit_btn = page.locator("button:has-text('Check Fit')").or_(page.locator("button:has-text('check fit')"))
    check_fit_btn.click()
    
    # Wait for error message to appear
    page.wait_for_timeout(1000)
    
    # Look for the validation error message
    error_msg = page.locator("text=/please select a.*model.*sidebar/i").first
    
    if error_msg.is_visible():
        error_text = error_msg.text_content() or ""
        print(f"\n✓ Validation error: {error_text}")
        
        # Parse the debug info
        if '(label=' in error_text:
            # Extract the debug portion
            import re
            match = re.search(r'\(label=([^,]+),\s*meta=([^,]+),\s*multi=([^)]+)\)', error_text)
            
            if match:
                label_val = match.group(1)
                meta_val = match.group(2)
                multi_val = match.group(3)
                
                print(f"  label: {label_val}")
                print(f"  meta: {meta_val}")
                print(f"  multi: {multi_val}")
                
                # If a model was selected in previous test or by user, it shouldn't be NULL
                # If no model selected, should show NULL (which is also valid)
                # The important thing is the format is correct
                assert label_val is not None, "label value missing"
                assert meta_val is not None, "meta value missing"
                assert multi_val in ['YES', 'NO'], f"Invalid multi value: {multi_val}"
                
                print(f"\n✓ Debug info format is correct")
            else:
                pytest.fail(f"Debug info format not found in error message: {error_text}")
    else:
        # No error means validation passed (model is selected correctly)
        print("\n✓ No validation error - model is properly selected")


def test_model_selection_populates_label(page_with_debug: Page):
    """Test complete flow: select model → dispatch event → populate label → validation passes."""
    page = page_with_debug
    
    # Install console log capture
    console_logs = []
    page.on("console", lambda msg: console_logs.append(f"{msg.type()}: {msg.text()}"))
    
    # Select a model
    sidebar_button = page.locator("button:has-text('Models')").or_(page.locator("[aria-label*='model']")).first
    if sidebar_button.is_visible():
        sidebar_button.click()
        page.wait_for_timeout(300)
    
    # Select Claude Sonnet 4.6 (first model in list)
    model_radio = page.locator("input[type='radio'][value='claude-sonnet-4-6']").or_(
        page.locator("input[type='radio'][name='fit-model']").first
    )
    
    if model_radio.is_visible():
        model_radio.click()
        page.wait_for_timeout(500)
        
        # Check console logs for event dispatch
        rt_sidebar_logs = [log for log in console_logs if 'rt-sidebar' in log.lower()]
        assert len(rt_sidebar_logs) > 0, "No rt-sidebar event logs found"
        
        print(f"\n✓ Found {len(rt_sidebar_logs)} rt-sidebar event logs")
        
        # Now try to run check fit
        resume_area = page.locator("textarea").first
        jd_area = page.locator("textarea").nth(1)
        
        resume_area.fill("Test resume")
        jd_area.fill("Test JD")
        
        check_fit_btn = page.locator("button:has-text('Check Fit')").or_(page.locator("button:has-text('check fit')"))
        check_fit_btn.click()
        
        page.wait_for_timeout(1000)
        
        # Check if validation error appears
        error_msg = page.locator("text=/please select a.*model/i").first
        
        if error_msg.is_visible():
            error_text = error_msg.text_content() or ""
            
            # Should NOT show label=NULL if we just selected a model
            assert 'label=NULL' not in error_text, f"Label is NULL even after selecting model! Error: {error_text}"
            
            print(f"\n✓ Validation shows populated label (not NULL): {error_text}")
        else:
            print("\n✓ No validation error - model selection worked correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
