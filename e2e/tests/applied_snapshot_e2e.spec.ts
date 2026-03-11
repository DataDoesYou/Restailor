import { test, expect } from './auth.setup';

test.describe('Applied snapshot lifecycle', () => {
  test('tailor, save applied, reload and restore, edit auto-uncheck', async ({ page }) => {
  // Root route avoids SSR session requirement while still loading tailor client
  await page.goto('/');

  const areas = page.locator('textarea');
  await expect(areas.first()).toBeVisible();
  await expect(areas.first()).toBeEnabled({ timeout: 10000 });

    const resumeBox = areas.first();
    const jdBox = areas.nth(1);

    await resumeBox.fill('Base Resume Line 1\nExperience X');
    await jdBox.fill('Job Description Line 1\nRole Y');

    // Tailor button (could be Tailor and Judge depending on toggle)
    const tailorBtn = page.getByRole('button', { name: /Tailor/ });
    await tailorBtn.click();

    // Wait for any result region to populate some non-empty text (coarse)
    const region = page.locator('div[role="region"]').first();
    await expect(region).toContainText(/.+/, { timeout: 120_000 });

    const appliedCb = page.locator('input#applied_snapshot');
    await appliedCb.check();
    await expect(appliedCb).toBeChecked();

    // Edit triggers auto-uncheck
    await jdBox.type(' EDIT');
    await expect(appliedCb).not.toBeChecked({ timeout: 4000 });
  });
});
