"""
End-to-end test for sidebar multi-model settings hydration and database persistence.

This test verifies:
1. Frontend hydration completes successfully
2. Save effect runs after hydration
3. Checkbox toggle triggers API call
4. Database is updated with correct values
5. Page refresh preserves the saved state
"""

import asyncio
import json
import time
from typing import Any, Dict, List

import psycopg2
import pytest
from playwright.sync_api import Page, expect, ConsoleMessage


def get_db_connection():
    """Get database connection using environment variables."""
    import os
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set")
    
    # Parse postgres:// URL
    # Format: postgresql://user:password@host:port/database
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgres://")
    
    return psycopg2.connect(db_url)


def clear_user_preferences(user_id: int):
    """Clear user preferences from database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_preferences WHERE user_id = %s", (user_id,))
            conn.commit()
    finally:
        conn.close()


def get_user_preferences(user_id: int) -> Dict[str, Any] | None:
    """Get user preferences from database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT settings, version, updated_at FROM user_preferences WHERE user_id = %s",
                (user_id,)
            )
            row = cur.fetchone()
            if row:
                return {
                    "settings": row[0],  # JSONB is returned as dict
                    "version": row[1],
                    "updated_at": row[2]
                }
            return None
    finally:
        conn.close()


class ConsoleLogCapture:
    """Capture and analyze console logs from the browser."""
    
    def __init__(self):
        self.logs: List[str] = []
    
    def handle(self, msg: ConsoleMessage):
        """Handle console message."""
        text = msg.text
        self.logs.append(text)
        print(f"[BROWSER CONSOLE] {text}")
    
    def has_log_containing(self, substring: str) -> bool:
        """Check if any log contains the substring."""
        return any(substring in log for log in self.logs)
    
    def get_logs_containing(self, substring: str) -> List[str]:
        """Get all logs containing the substring."""
        return [log for log in self.logs if substring in log]
    
    def clear(self):
        """Clear captured logs."""
        self.logs.clear()


@pytest.fixture
def console_capture():
    """Fixture to provide console log capture."""
    return ConsoleLogCapture()


@pytest.fixture
def setup_test_user():
    """Setup test user and clear preferences before test."""
    # For this test, we'll use user_id = 1 (assuming it exists)
    # In a real scenario, you'd create a test user
    user_id = 1
    clear_user_preferences(user_id)
    yield user_id
    # Cleanup after test
    clear_user_preferences(user_id)


def test_sidebar_hydration_completes(page: Page, console_capture: ConsoleLogCapture, setup_test_user):
    """Test that sidebar hydration completes successfully."""
    user_id = setup_test_user
    
    # Setup console logging
    page.on("console", console_capture.handle)
    
    # Navigate to home page (or any page with sidebar)
    page.goto("http://localhost:3000/")
    
    # Wait for initial page load
    page.wait_for_load_state("networkidle")
    
    # Wait a bit for React hydration
    time.sleep(2)
    
    # Check that hydration completed
    assert console_capture.has_log_containing("[SidebarModels] Initial hydration complete"), \
        "Hydration did not complete. Logs:\n" + "\n".join(console_capture.logs)
    
    # Verify hydration logs appear in correct order
    hydration_logs = [log for log in console_capture.logs if "[SidebarModels]" in log]
    print("\n=== Hydration Logs ===")
    for log in hydration_logs:
        print(log)
    
    # Should see initial hydration effect run
    assert any("Hydration effect running" in log for log in hydration_logs), \
        "Hydration effect did not run"


def test_sidebar_checkbox_saves_to_database(
    page: Page, 
    console_capture: ConsoleLogCapture, 
    setup_test_user
):
    """Test that toggling multi-model checkbox saves to database."""
    user_id = setup_test_user
    
    # Setup console logging
    page.on("console", console_capture.handle)
    
    # Navigate to home page
    page.goto("http://localhost:3000/")
    page.wait_for_load_state("networkidle")
    
    # Wait for hydration to complete
    time.sleep(2)
    
    # Clear logs to focus on save flow
    console_capture.clear()
    
    # Find and click the multi-model checkbox
    # Look for checkbox with label containing "Multi-model"
    checkbox = page.locator('input[type="checkbox"]').filter(
        has=page.locator('text=/Multi.*model/i')
    ).first
    
    # If not found, try alternative selectors
    if checkbox.count() == 0:
        # Try finding by nearby text
        checkbox = page.locator('label:has-text("Multi-model")').locator('input[type="checkbox"]')
    
    if checkbox.count() == 0:
        # Get all checkboxes and print for debugging
        all_checkboxes = page.locator('input[type="checkbox"]').all()
        print(f"\n=== Found {len(all_checkboxes)} checkboxes ===")
        pytest.fail("Could not find multi-model checkbox")
    
    # Check initial state
    is_checked = checkbox.is_checked()
    print(f"\n=== Initial checkbox state: {is_checked} ===")
    
    # Click checkbox to toggle
    checkbox.click()
    
    # Wait for save to complete
    time.sleep(2)
    
    # Verify save flow in logs
    print("\n=== Save Flow Logs ===")
    save_logs = console_capture.get_logs_containing("[SidebarModels]")
    for log in save_logs:
        print(log)
    
    # Should see save effect run
    assert console_capture.has_log_containing("Save effect triggered"), \
        "Save effect did not trigger. Logs:\n" + "\n".join(console_capture.logs)
    
    # Should see API call
    assert console_capture.has_log_containing("[apiClient]") or \
           console_capture.has_log_containing("Making PUT request"), \
        "API call was not made. Logs:\n" + "\n".join(console_capture.logs)
    
    # Should see save success
    assert console_capture.has_log_containing("Save succeeded"), \
        "Save did not succeed. Logs:\n" + "\n".join(console_capture.logs)
    
    # Verify database was updated
    prefs = get_user_preferences(user_id)
    assert prefs is not None, "User preferences not found in database"
    
    print(f"\n=== Database State ===")
    print(f"Settings: {json.dumps(prefs['settings'], indent=2)}")
    print(f"Version: {prefs['version']}")
    
    # Verify settings structure
    settings = prefs["settings"]
    assert "multi_model_enabled" in settings, "multi_model_enabled not in settings"
    
    # Verify checkbox state matches database
    expected_state = not is_checked
    assert settings["multi_model_enabled"] == expected_state, \
        f"Database state {settings['multi_model_enabled']} doesn't match expected {expected_state}"


def test_sidebar_state_persists_across_refresh(
    page: Page,
    console_capture: ConsoleLogCapture,
    setup_test_user
):
    """Test that sidebar state persists after page refresh."""
    user_id = setup_test_user
    
    # Setup console logging
    page.on("console", console_capture.handle)
    
    # Navigate to home page
    page.goto("http://localhost:3000/")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    
    # Find checkbox
    checkbox = page.locator('input[type="checkbox"]').filter(
        has=page.locator('text=/Multi.*model/i')
    ).first
    
    if checkbox.count() == 0:
        checkbox = page.locator('label:has-text("Multi-model")').locator('input[type="checkbox"]')
    
    # Enable multi-model
    if not checkbox.is_checked():
        checkbox.click()
        time.sleep(2)
    
    # Verify it's checked
    assert checkbox.is_checked(), "Checkbox should be checked after click"
    
    # Refresh the page
    console_capture.clear()
    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    
    # Find checkbox again (DOM recreated)
    checkbox = page.locator('input[type="checkbox"]').filter(
        has=page.locator('text=/Multi.*model/i')
    ).first
    
    if checkbox.count() == 0:
        checkbox = page.locator('label:has-text("Multi-model")').locator('input[type="checkbox"]')
    
    # Verify it's still checked (loaded from database)
    assert checkbox.is_checked(), "Checkbox state should persist after refresh"
    
    # Verify hydration loaded from database
    assert console_capture.has_log_containing("GET /users/me/model-settings") or \
           console_capture.has_log_containing("calling GET"), \
        "Should have fetched settings from API on hydration"


def test_sidebar_toggle_updates_database_version(
    page: Page,
    console_capture: ConsoleLogCapture,
    setup_test_user
):
    """Test that toggling checkbox increments version in database."""
    user_id = setup_test_user
    
    page.on("console", console_capture.handle)
    page.goto("http://localhost:3000/")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    
    # Find checkbox
    checkbox = page.locator('input[type="checkbox"]').filter(
        has=page.locator('text=/Multi.*model/i')
    ).first
    
    if checkbox.count() == 0:
        checkbox = page.locator('label:has-text("Multi-model")').locator('input[type="checkbox"]')
    
    # First toggle
    checkbox.click()
    time.sleep(2)
    
    prefs1 = get_user_preferences(user_id)
    assert prefs1 is not None, "Preferences should exist after first toggle"
    version1 = prefs1["version"]
    print(f"\n=== After first toggle: version={version1} ===")
    
    # Second toggle
    checkbox.click()
    time.sleep(2)
    
    prefs2 = get_user_preferences(user_id)
    assert prefs2 is not None, "Preferences should exist after second toggle"
    version2 = prefs2["version"]
    print(f"=== After second toggle: version={version2} ===")
    
    # Version should increment
    assert version2 > version1, \
        f"Version should increment (was {version1}, now {version2})"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
