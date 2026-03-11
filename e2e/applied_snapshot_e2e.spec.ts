import { test, expect } from '@playwright/test';

// Basic end-to-end covering applied snapshot lifecycle.
// Assumes user is already authenticated via prior storageState or session cookie.

test.describe('Applied snapshot lifecycle', () => {
  test('tailor, save applied, reload and restore, edit auto-uncheck', async ({ page }) => {
    // Navigate to tailor page
    await page.goto('/tailor');

    const resumeBox = page.locator('textarea').first();
    const jdBox = page.locator('textarea').nth(1);

    await resumeBox.fill('Base Resume Line 1\nExperience X');
    await jdBox.fill('Job Description Line 1\nRole Y');

  // Trigger tailor only
    const tailorBtn = page.getByRole('button', { name: /Tailor/ });
    await tailorBtn.click();

    // Wait for some output box to receive content (tailored)
    await expect(page.locator('div[role="region"]')).toContainText(/.+/,{ timeout: 60000 });

    // Mark applied
    const appliedCb = page.locator('input#applied_snapshot');
    await appliedCb.check();
    await expect(appliedCb).toBeChecked();

    // Reload page and re-paste same inputs to trigger auto-restore
    await page.reload();
    await resumeBox.fill('Base Resume Line 1\nExperience X');
    await jdBox.fill('Job Description Line 1\nRole Y');

    // Expect applied checkbox to auto-check after debounce
    await expect(appliedCb).toBeChecked({ timeout: 5000 });

    // Edit JD to auto-uncheck
    await jdBox.type(' EDIT');
    await expect(appliedCb).not.toBeChecked({ timeout: 3000 });
  });
});
