import { test, expect } from './auth.setup';
import type { Page, Route } from '@playwright/test';

/**
 * Pessimistic Pattern Tests: Applied Checkbox
 * 
 * Proves that the Applied checkbox follows the pessimistic pattern:
 * 1. Checkbox stays disabled until server responds
 * 2. UI state reflects server response ONLY (no optimistic updates)
 * 3. Page reload shows state from /applications/list (database is source of truth)
 * 4. On server error (500), checkbox does NOT change state
 */

test.describe('Applied checkbox - Pessimistic pattern', () => {
  
  test.beforeEach(async ({ page }) => {
    // Navigate to Resume Tailor page
    await page.goto('http://localhost:3000/resume');
    
    // Fill in resume and JD to enable checkbox
    const resumeBox = page.locator('textarea').first();
    const jdBox = page.locator('textarea').nth(1);
    
    await resumeBox.fill('Software Engineer with 5 years experience\nPython, TypeScript, React');
    await jdBox.fill('Senior Developer position\nRequired: 5+ years Python');
    
    // Wait for page to be ready
    await page.waitForLoadState('networkidle');
  });

  test('checkbox stays disabled until server responds', async ({ page }) => {
    const checkbox = page.locator('input#applied_snapshot');
    
    // Initially unchecked and enabled
    await expect(checkbox).not.toBeChecked();
    await expect(checkbox).toBeEnabled();
    
    // Intercept the POST request to add delay
    let requestStarted = false;
    let requestCompleted = false;
    
    await page.route('**/applications/jd/apply', async (route: Route) => {
      requestStarted = true;
      
      // Add artificial delay to simulate slow network
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Continue with the request
      await route.continue();
      requestCompleted = true;
    });
    
    // Click checkbox
    await checkbox.click();
    
    // Immediately after click, checkbox should be disabled (pessimistic)
    await expect(checkbox).toBeDisabled();
    
    // Verify request started
    expect(requestStarted).toBe(true);
    
    // Wait for spinner to appear
    const spinner = page.locator('div[title="Saving..."]');
    await expect(spinner).toBeVisible();
    
    // Checkbox should STILL be disabled while request is in flight
    await expect(checkbox).toBeDisabled();
    
    // Wait for request to complete
    await page.waitForResponse(response => 
      response.url().includes('/applications/jd/apply') && response.status() === 200
    );
    
    expect(requestCompleted).toBe(true);
    
    // After response, checkbox should be enabled and checked
    await expect(checkbox).toBeEnabled();
    await expect(checkbox).toBeChecked();
    
    // Spinner should disappear
    await expect(spinner).not.toBeVisible();
  });

  test('checkbox reflects server response only (no optimistic update)', async ({ page }) => {
    const checkbox = page.locator('input#applied_snapshot');
    
    // Intercept and mock server response
    let serverCheckedState = false;
    
    await page.route('**/applications/jd/apply', async (route: Route) => {
      const method = route.request().method();
      
      if (method === 'POST') {
        // Server sets applied = true
        serverCheckedState = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            jdHash: 'test-hash',
            appliedKey: 'test-key',
            updatedAt: new Date().toISOString(),
            isApplied: true // Server says TRUE
          })
        });
      }
    });
    
    // Click checkbox
    await checkbox.click();
    
    // Wait for request to complete
    await page.waitForResponse(response => 
      response.url().includes('/applications/jd/apply')
    );
    
    // Checkbox should match server response (true)
    await expect(checkbox).toBeChecked();
    expect(serverCheckedState).toBe(true);
    
    // Now test unchecking
    await page.route('**/applications/jd/apply', async (route: Route) => {
      const method = route.request().method();
      
      if (method === 'DELETE') {
        // Server sets applied = false
        serverCheckedState = false;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            jdHash: 'test-hash',
            appliedKey: 'test-key',
            changed: true,
            isApplied: false // Server says FALSE
          })
        });
      }
    });
    
    // Uncheck
    await checkbox.click();
    
    await page.waitForResponse(response => 
      response.url().includes('/applications/jd/apply')
    );
    
    // Checkbox should match server response (false)
    await expect(checkbox).not.toBeChecked();
    expect(serverCheckedState).toBe(false);
  });

  test('on server error (500), checkbox does NOT change', async ({ page }) => {
    const checkbox = page.locator('input#applied_snapshot');
    
    // Get initial state
    const initialCheckedState = await checkbox.isChecked();
    
    // Intercept and return 500 error
    await page.route('**/applications/jd/apply', async (route: Route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Internal server error'
        })
      });
    });
    
    // Try to click checkbox
    await checkbox.click();
    
    // Wait a moment for error handling
    await page.waitForTimeout(500);
    
    // Checkbox should remain in ORIGINAL state (pessimistic - no change on error)
    if (initialCheckedState) {
      await expect(checkbox).toBeChecked();
    } else {
      await expect(checkbox).not.toBeChecked();
    }
    
    // Error banner should show
    const banner = page.locator('text=/Failed to save/i');
    await expect(banner).toBeVisible({ timeout: 2000 });
    
    // Banner should show HTTP status
    await expect(banner).toContainText('500');
  });

  test('page reload shows state from server (database as source of truth)', async ({ page }) => {
    const checkbox = page.locator('input#applied_snapshot');
    
    // Mock server to return isApplied: true
    await page.route('**/applications/jd/apply', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          jdHash: 'test-hash-123',
          appliedKey: 'user:test-hash-123:base-hash',
          updatedAt: new Date().toISOString(),
          isApplied: true
        })
      });
    });
    
    // Check the checkbox
    await checkbox.click();
    await page.waitForResponse(response => 
      response.url().includes('/applications/jd/apply')
    );
    await expect(checkbox).toBeChecked();
    
    // Mock /applications/list to return the applied state
    await page.route('**/applications/list*', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            appliedKey: 'user:test-hash-123:base-hash',
            jdHash: 'test-hash-123',
            baseHash: 'base-hash',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            isApplied: true, // Database says TRUE
            interviewing: false,
            offer: false,
            hired: false
          }],
          total: 1,
          page: 1,
          page_size: 20,
          total_pages: 1
        })
      });
    });
    
    // Reload page
    await page.reload();
    
    // Re-fill inputs to trigger restore logic
    const resumeBox = page.locator('textarea').first();
    const jdBox = page.locator('textarea').nth(1);
    await resumeBox.fill('Software Engineer with 5 years experience\nPython, TypeScript, React');
    await jdBox.fill('Senior Developer position\nRequired: 5+ years Python');
    
    // Wait for debounce and auto-restore
    await page.waitForTimeout(1500);
    
    // Checkbox should reflect database state (checked)
    await expect(checkbox).toBeChecked({ timeout: 5000 });
  });

  test('concurrent requests are prevented (double-click protection)', async ({ page }) => {
    const checkbox = page.locator('input#applied_snapshot');
    
    let requestCount = 0;
    
    await page.route('**/applications/jd/apply', async (route: Route) => {
      requestCount++;
      
      // Add delay to ensure second click happens while first is pending
      await new Promise(resolve => setTimeout(resolve, 500));
      
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          jdHash: 'test-hash',
          appliedKey: 'test-key',
          updatedAt: new Date().toISOString(),
          isApplied: true
        })
      });
    });
    
    // Double-click rapidly
    await checkbox.click();
    await checkbox.click(); // Should be blocked (disabled)
    await checkbox.click(); // Should be blocked (disabled)
    
    // Wait for request to complete
    await page.waitForTimeout(1000);
    
    // Only ONE request should have been sent (double-click prevented)
    expect(requestCount).toBe(1);
  });

  test('shows detailed error message with HTTP status', async ({ page }) => {
    const checkbox = page.locator('input#applied_snapshot');
    
    // Mock 422 validation error
    await page.route('**/applications/jd/apply', async (route: Route) => {
      await route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Invalid jdHash format'
        })
      });
    });
    
    await checkbox.click();
    await page.waitForTimeout(500);
    
    // Error banner should show status code and error detail
    const banner = page.locator('div:has-text("Failed to save")');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('422');
    await expect(banner).toContainText('Invalid jdHash format');
  });

  test('aria-busy attribute reflects loading state', async ({ page }) => {
    const checkbox = page.locator('input#applied_snapshot');
    
    // Initially not busy
    await expect(checkbox).not.toHaveAttribute('aria-busy', 'true');
    
    // Delay the response
    await page.route('**/applications/jd/apply', async (route: Route) => {
      await new Promise(resolve => setTimeout(resolve, 500));
      await route.continue();
    });
    
    // Click checkbox
    await checkbox.click();
    
    // Should be aria-busy during request
    await expect(checkbox).toHaveAttribute('aria-busy', 'true');
    
    // Wait for completion
    await page.waitForResponse(response => 
      response.url().includes('/applications/jd/apply')
    );
    
    // No longer busy after response
    await expect(checkbox).not.toHaveAttribute('aria-busy', 'true');
  });

  test('screen reader announcement (aria-live) appears during save', async ({ page }) => {
    const checkbox = page.locator('input#applied_snapshot');
    
    // Delay response
    await page.route('**/applications/jd/apply', async (route: Route) => {
      await new Promise(resolve => setTimeout(resolve, 800));
      await route.continue();
    });
    
    // Click checkbox
    await checkbox.click();
    
    // Screen reader text should appear
    const srText = page.locator('text=/Saving applied status/i');
    await expect(srText).toBeVisible();
    
    // Wait for completion
    await page.waitForResponse(response => 
      response.url().includes('/applications/jd/apply')
    );
    
    // Screen reader text should disappear
    await expect(srText).not.toBeVisible();
  });
});
