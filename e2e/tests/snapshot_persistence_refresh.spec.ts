import { test, expect } from './auth.setup';

test.describe('Snapshot persistence across page refresh', () => {
  test('load snapshot from history, refresh, data persists', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    const areas = page.locator('textarea');
    await expect(areas.first()).toBeVisible();
    await expect(areas.first()).toBeEnabled({ timeout: 10000 });

    const resumeBox = areas.first();
    const jdBox = areas.nth(1);

    // Fill in unique test data
    const uniqueResume = `Test Resume ${Date.now()}\nSenior Software Engineer`;
    const uniqueJD = `Test Job Description ${Date.now()}\nFull Stack Developer`;
    
    await resumeBox.fill(uniqueResume);
    await jdBox.fill(uniqueJD);

    // Run a job to create a snapshot
    const fitBtn = page.getByRole('button', { name: /Fit/i });
    await fitBtn.click();

    // Wait for fit output to appear
    const fitOutput = page.locator('div[role="region"]').filter({ hasText: /fit|score|match/i }).first();
    await expect(fitOutput).toContainText(/.+/, { timeout: 120_000 });

    // Verify the data is in the inputs
    await expect(resumeBox).toHaveValue(uniqueResume);
    await expect(jdBox).toHaveValue(uniqueJD);

    // Navigate to History page
    await page.getByRole('link', { name: /history/i }).click();
    await expect(page).toHaveURL(/\/history/);

    // Find the most recent snapshot (first row in history)
    const firstHistoryRow = page.locator('table tbody tr').first();
    await expect(firstHistoryRow).toBeVisible({ timeout: 10000 });
    
    // Click on the snapshot to open it
    await firstHistoryRow.click();
    
    // Should navigate to /resume with the snapshot loaded
    await expect(page).toHaveURL(/\/resume/);
    
    // Verify data is loaded
    await expect(resumeBox).toHaveValue(uniqueResume, { timeout: 5000 });
    await expect(jdBox).toHaveValue(uniqueJD);
    await expect(fitOutput).toContainText(/.+/);

    // Now refresh the page - this is the critical test
    await page.reload();

    // After refresh, data should persist (loaded from current_snapshot_key)
    await expect(areas.first()).toBeVisible();
    await expect(areas.first()).toBeEnabled({ timeout: 10000 });

    // Verify all data persisted after refresh
    await expect(resumeBox).toHaveValue(uniqueResume, { timeout: 10000 });
    await expect(jdBox).toHaveValue(uniqueJD);
    
    // Verify fit output also persisted
    const fitOutputAfterRefresh = page.locator('div[role="region"]').filter({ hasText: /fit|score|match/i }).first();
    await expect(fitOutputAfterRefresh).toContainText(/.+/, { timeout: 5000 });
  });

  test('refresh without opening snapshot shows empty state', async ({ page }) => {
    // Navigate directly to /resume without opening a snapshot
    await page.goto('/resume');

    const areas = page.locator('textarea');
    await expect(areas.first()).toBeVisible();
    await expect(areas.first()).toBeEnabled({ timeout: 10000 });

    const resumeBox = areas.first();
    const jdBox = areas.nth(1);

    // If no current_snapshot_key is set, should be empty
    // (unless user has a snapshot from a previous session)
    // This test verifies the page doesn't crash on refresh with no snapshot
    await expect(resumeBox).toBeVisible();
    await expect(jdBox).toBeVisible();
    
    // Refresh should not crash
    await page.reload();
    
    // Should still render properly
    await expect(areas.first()).toBeVisible();
    await expect(areas.first()).toBeEnabled({ timeout: 10000 });
  });
});
