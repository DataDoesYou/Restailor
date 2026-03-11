import { test, expect } from './auth.setup';

// Basic smoke test for History page rendering and controls
// Assumes backend and frontend are started via Playwright webServer config.

test.describe('History page UI', () => {
  test('renders and shows independent I/O/H filters and table headers', async ({ page }) => {
    // Navigate directly to Next.js history route
    await page.goto('http://localhost:3000/history');

    // Wait for heading
    await expect(page.getByRole('heading', { name: 'History' })).toBeVisible();

    // Check filter controls exist
    await expect(page.getByLabel('Applied')).toBeVisible();
    await expect(page.getByLabel('Interviewing')).toBeVisible();
    await expect(page.getByLabel('Offer')).toBeVisible();
    await expect(page.getByLabel('Hired')).toBeVisible();

    // Table headers
    await expect(page.getByRole('columnheader', { name: /Actions/ })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Created/ })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Job Description Snippet/ })).toBeVisible();
  });
});
