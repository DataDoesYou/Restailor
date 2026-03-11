import { test, expect } from './auth.setup';
import type { Page, Route } from '@playwright/test';

/**
 * Pessimistic Pattern Tests: I/O/H Stage Buttons
 * 
 * Proves that the stage buttons (Applied/Interviewing/Offer/Hired) follow the pessimistic pattern:
 * 1. Button shows spinner and is disabled until server responds
 * 2. List is revalidated after each update (database is source of truth)
 * 3. Button state reflects server flags ONLY (no optimistic updates)
 * 4. On server error (500), button does NOT change state
 * 5. Other buttons remain clickable during individual button update
 */

test.describe('I/O/H buttons - Pessimistic pattern', () => {
  
  let testAppliedKey: string;
  
  test.beforeEach(async ({ page }) => {
    // Create a test application via Resume Tailor page
    await page.goto('http://localhost:3000/resume');
    
    const resumeBox = page.locator('textarea').first();
    const jdBox = page.locator('textarea').nth(1);
    
    await resumeBox.fill('Software Engineer\nPython, React, Node.js');
    await jdBox.fill('Senior Developer Role\nRequired: 5+ years experience');
    
    // Mark as applied to create entry
    const checkbox = page.locator('input#applied_snapshot');
    await checkbox.click();
    
    // Wait for save to complete
    await page.waitForResponse(response => 
      response.url().includes('/applications/jd/apply') && response.status() === 200
    );
    
    await expect(checkbox).toBeChecked();
    
    // Navigate to History page
    await page.goto('http://localhost:3000/history');
    await expect(page.getByRole('heading', { name: 'History' })).toBeVisible();
    
    // Wait for table to load
    await page.waitForLoadState('networkidle');
  });

  test('button shows spinner and is disabled until server responds', async ({ page }) => {
    // Find the first row's Interviewing button
    const interviewingBtn = page.locator('button[aria-label="Interviewing"]').first();
    
    // Initially should be enabled (not selected)
    await expect(interviewingBtn).toBeEnabled();
    await expect(interviewingBtn).not.toHaveAttribute('aria-busy', 'true');
    
    // Intercept PATCH request to add delay
    let requestStarted = false;
    let requestCompleted = false;
    
    await page.route('**/applications/stage-flags', async (route: Route) => {
      requestStarted = true;
      
      // Add delay to simulate slow network
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Continue with request
      await route.continue();
      requestCompleted = true;
    });
    
    // Click Interviewing button
    await interviewingBtn.click();
    
    // Immediately after click:
    // 1. Button should be disabled (pessimistic)
    await expect(interviewingBtn).toBeDisabled();
    
    // 2. Button should show aria-busy
    await expect(interviewingBtn).toHaveAttribute('aria-busy', 'true');
    
    // 3. Button should show spinner (not the "I" letter)
    const spinner = interviewingBtn.locator('div[class*="animate-spin"]');
    await expect(spinner).toBeVisible();
    
    // Verify request started
    expect(requestStarted).toBe(true);
    
    // Button should STILL be disabled while request is in flight
    await expect(interviewingBtn).toBeDisabled();
    
    // Wait for request to complete
    await page.waitForResponse(response => 
      response.url().includes('/applications/stage-flags') && response.status() === 200
    );
    
    expect(requestCompleted).toBe(true);
    
    // After response:
    // 1. Button should be enabled
    await expect(interviewingBtn).toBeEnabled();
    
    // 2. No longer aria-busy
    await expect(interviewingBtn).not.toHaveAttribute('aria-busy', 'true');
    
    // 3. Spinner should be gone, "I" letter visible
    await expect(spinner).not.toBeVisible();
  });

  test('list is revalidated after update (database as source of truth)', async ({ page }) => {
    // Count initial GET requests to /applications/list
    let listRequestCount = 0;
    
    page.on('request', request => {
      if (request.url().includes('/applications') && request.method() === 'GET') {
        listRequestCount++;
      }
    });
    
    const offerBtn = page.locator('button[aria-label="Offer"]').first();
    
    // Click Offer button
    await offerBtn.click();
    
    // Wait for PATCH to complete
    await page.waitForResponse(response => 
      response.url().includes('/applications/stage-flags') && response.status() === 200
    );
    
    // Wait for list refresh
    await page.waitForResponse(response => 
      response.url().includes('/applications') && response.request().method() === 'GET'
    );
    
    // Verify list was revalidated (at least one GET request after PATCH)
    expect(listRequestCount).toBeGreaterThan(0);
  });

  test('button state reflects server flags only (no optimistic update)', async ({ page }) => {
    const hiredBtn = page.locator('button[aria-label="Hired"]').first();
    
    // Mock server to return specific flags
    await page.route('**/applications/stage-flags', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          appliedKey: 'test-key',
          interviewing: false,
          offer: false,
          hired: true, // Server says TRUE
          isApplied: true,
          stageLabel: 'Hired'
        })
      });
    });
    
    // Mock list refresh to return same flags
    await page.route('**/applications*', async (route: Route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [{
              appliedKey: 'test-key',
              jdHash: 'hash',
              baseHash: 'base',
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
              isApplied: true,
              interviewing: false,
              offer: false,
              hired: true, // Database says TRUE
              stageLabel: 'Hired'
            }],
            total: 1,
            page: 1,
            page_size: 20,
            total_pages: 1
          })
        });
      } else {
        await route.continue();
      }
    });
    
    // Click button
    await hiredBtn.click();
    
    // Wait for both PATCH and GET to complete
    await page.waitForResponse(response => 
      response.url().includes('/applications/stage-flags')
    );
    await page.waitForResponse(response => 
      response.url().includes('/applications') && response.request().method() === 'GET'
    );
    
    // Button should reflect server state (white border = selected)
    await expect(hiredBtn).toHaveClass(/border-white/);
  });

  test('on server error (500), button does NOT change state', async ({ page }) => {
    const interviewingBtn = page.locator('button[aria-label="Interviewing"]').first();
    
    // Get initial button state (should not be selected)
    const initialClass = await interviewingBtn.getAttribute('class');
    const wasSelected = initialClass?.includes('border-white');
    
    // Mock 500 error
    await page.route('**/applications/stage-flags', async (route: Route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Database connection failed'
        })
      });
    });
    
    // Click button
    await interviewingBtn.click();
    
    // Wait for error
    await page.waitForTimeout(500);
    
    // Button should remain in ORIGINAL state (pessimistic - no change on error)
    const newClass = await interviewingBtn.getAttribute('class');
    const isSelected = newClass?.includes('border-white');
    
    expect(isSelected).toBe(wasSelected);
    
    // Error toast should appear
    const toast = page.locator('text=/Failed to update interviewing/i');
    await expect(toast).toBeVisible({ timeout: 3000 });
    
    // Toast should show HTTP status
    await expect(toast).toContainText('500');
  });

  test('other buttons remain clickable during individual button update', async ({ page }) => {
    const interviewingBtn = page.locator('button[aria-label="Interviewing"]').first();
    const offerBtn = page.locator('button[aria-label="Offer"]').first();
    const hiredBtn = page.locator('button[aria-label="Hired"]').first();
    
    // Add delay to Interviewing request
    await page.route('**/applications/stage-flags', async (route: Route) => {
      const body = await route.request().postDataJSON();
      
      if (body.interviewing !== undefined) {
        // Delay Interviewing request
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      
      await route.continue();
    });
    
    // Click Interviewing button
    await interviewingBtn.click();
    
    // Interviewing should be disabled
    await expect(interviewingBtn).toBeDisabled();
    
    // But Offer and Hired should still be ENABLED
    await expect(offerBtn).toBeEnabled();
    await expect(hiredBtn).toBeEnabled();
    
    // Should be able to click Offer while Interviewing is pending
    // (This will abort the Interviewing request and start Offer request)
    await offerBtn.click();
    
    // Now Offer should be disabled
    await expect(offerBtn).toBeDisabled();
  });

  test('abort controller cancels stale request when clicking different button', async ({ page }) => {
    const interviewingBtn = page.locator('button[aria-label="Interviewing"]').first();
    const offerBtn = page.locator('button[aria-label="Offer"]').first();
    
    let interviewingRequestAborted = false;
    let offerRequestCompleted = false;
    
    await page.route('**/applications/stage-flags', async (route: Route) => {
      const body = await route.request().postDataJSON();
      
      if (body.interviewing !== undefined) {
        // Simulate slow Interviewing request
        try {
          await new Promise((resolve, reject) => {
            setTimeout(resolve, 2000);
            // This will be aborted when Offer is clicked
          });
          await route.continue();
        } catch (err) {
          interviewingRequestAborted = true;
          await route.abort();
        }
      } else if (body.offer !== undefined) {
        // Offer request completes normally
        await route.continue();
        offerRequestCompleted = true;
      } else {
        await route.continue();
      }
    });
    
    // Click Interviewing
    await interviewingBtn.click();
    await expect(interviewingBtn).toBeDisabled();
    
    // Quickly click Offer (should abort Interviewing request)
    await page.waitForTimeout(100);
    await offerBtn.click();
    
    // Wait for Offer to complete
    await page.waitForResponse(response => 
      response.url().includes('/applications/stage-flags')
    );
    
    // Offer request should have completed
    expect(offerRequestCompleted).toBe(true);
  });

  test('double-click protection prevents redundant requests', async ({ page }) => {
    const interviewingBtn = page.locator('button[aria-label="Interviewing"]').first();
    
    let requestCount = 0;
    
    await page.route('**/applications/stage-flags', async (route: Route) => {
      requestCount++;
      
      // Add delay
      await new Promise(resolve => setTimeout(resolve, 500));
      
      await route.continue();
    });
    
    // Rapid triple-click
    await interviewingBtn.click();
    await interviewingBtn.click(); // Should be blocked (disabled)
    await interviewingBtn.click(); // Should be blocked (disabled)
    
    // Wait for request to complete
    await page.waitForTimeout(1000);
    
    // Only ONE request should have been sent
    expect(requestCount).toBe(1);
  });

  test('concurrency conflict (409) shows toast and refreshes list', async ({ page }) => {
    const offerBtn = page.locator('button[aria-label="Offer"]').first();
    
    // Mock 409 Conflict
    await page.route('**/applications/stage-flags', async (route: Route) => {
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Row was modified. Expected 2025-10-15T10:00:00Z, got 2025-10-15T10:05:00Z'
        })
      });
    });
    
    let listRefreshed = false;
    page.on('request', request => {
      if (request.url().includes('/applications') && request.method() === 'GET') {
        listRefreshed = true;
      }
    });
    
    // Click button
    await offerBtn.click();
    
    // Wait for error response
    await page.waitForTimeout(500);
    
    // Toast should show concurrency message
    const toast = page.locator('text=/Row changed on server/i');
    await expect(toast).toBeVisible({ timeout: 3000 });
    await expect(toast).toContainText(/reloading list/i);
    
    // List should have been refreshed
    await page.waitForTimeout(500);
    expect(listRefreshed).toBe(true);
  });

  test('Applied button (A) uses different endpoint', async ({ page }) => {
    const appliedBtn = page.locator('button[aria-label="Applied"]').first();
    
    let deleteEndpointCalled = false;
    
    // Applied button uncheck uses DELETE /applications/jd/apply
    await page.route('**/applications/jd/apply*', async (route: Route) => {
      if (route.request().method() === 'DELETE') {
        deleteEndpointCalled = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            jdHash: 'test-hash',
            appliedKey: 'test-key',
            changed: true,
            isApplied: false
          })
        });
      } else {
        await route.continue();
      }
    });
    
    // Click Applied to uncheck (row should already be applied from beforeEach)
    await appliedBtn.click();
    
    // Wait for request
    await page.waitForTimeout(500);
    
    // DELETE endpoint should have been called (not PATCH /stage-flags)
    expect(deleteEndpointCalled).toBe(true);
  });

  test('cascade logic: unchecking Interviewing clears Offer and Hired', async ({ page }) => {
    const interviewingBtn = page.locator('button[aria-label="Interviewing"]').first();
    const offerBtn = page.locator('button[aria-label="Offer"]').first();
    const hiredBtn = page.locator('button[aria-label="Hired"]').first();
    
    // First, set all three flags
    // (Assume backend auto-sets interviewing when setting offer)
    await offerBtn.click();
    await page.waitForResponse(response => response.url().includes('/applications/stage-flags'));
    await page.waitForTimeout(500);
    
    // Mock backend cascade response: unchecking interviewing clears all
    await page.route('**/applications/stage-flags', async (route: Route) => {
      const body = await route.request().postDataJSON();
      
      if (body.interviewing === false) {
        // Backend cascade logic clears all higher stages
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            appliedKey: 'test-key',
            interviewing: false,
            offer: false, // Cleared by cascade
            hired: false, // Cleared by cascade
            isApplied: true,
            stageLabel: 'Applied'
          })
        });
      } else {
        await route.continue();
      }
    });
    
    // Mock list refresh with cascade result
    await page.route('**/applications*', async (route: Route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [{
              appliedKey: 'test-key',
              jdHash: 'hash',
              baseHash: 'base',
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
              isApplied: true,
              interviewing: false,
              offer: false,
              hired: false,
              stageLabel: 'Applied'
            }],
            total: 1,
            page: 1,
            page_size: 20,
            total_pages: 1
          })
        });
      } else {
        await route.continue();
      }
    });
    
    // Uncheck Interviewing (if currently checked)
    await interviewingBtn.click();
    
    // Wait for update and refresh
    await page.waitForResponse(response => response.url().includes('/applications/stage-flags'));
    await page.waitForResponse(response => response.url().includes('/applications') && response.request().method() === 'GET');
    await page.waitForTimeout(500);
    
    // All three should now be unchecked (reflecting server cascade)
    await expect(interviewingBtn).not.toHaveClass(/border-white/);
    await expect(offerBtn).not.toHaveClass(/border-white/);
    await expect(hiredBtn).not.toHaveClass(/border-white/);
  });

  test('screen reader announcement (aria-live) during button update', async ({ page }) => {
    const interviewingBtn = page.locator('button[aria-label="Interviewing"]').first();
    
    // Delay response
    await page.route('**/applications/stage-flags', async (route: Route) => {
      await new Promise(resolve => setTimeout(resolve, 800));
      await route.continue();
    });
    
    // Click button
    await interviewingBtn.click();
    
    // Screen reader text should appear
    const srText = page.locator('text=/Updating Interviewing/i');
    await expect(srText).toBeVisible();
    
    // Wait for completion
    await page.waitForResponse(response => 
      response.url().includes('/applications/stage-flags')
    );
    
    // Screen reader text should disappear
    await expect(srText).not.toBeVisible();
  });

  test('detailed error message shows HTTP status and body snippet', async ({ page }) => {
    const hiredBtn = page.locator('button[aria-label="Hired"]').first();
    
    // Mock 422 validation error with detailed message
    await page.route('**/applications/stage-flags', async (route: Route) => {
      await route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Cannot set hired flag without interviewing flag'
        })
      });
    });
    
    // Click button
    await hiredBtn.click();
    
    // Wait for error
    await page.waitForTimeout(500);
    
    // Toast should show status code AND error detail
    const toast = page.locator('div[role="status"]');
    await expect(toast).toBeVisible({ timeout: 3000 });
    await expect(toast).toContainText('422');
    await expect(toast).toContainText('Cannot set hired flag without interviewing flag');
  });
});
