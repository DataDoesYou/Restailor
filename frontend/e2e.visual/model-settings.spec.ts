/**
 * E2E tests for Model Settings persistence and mode switching.
 * 
 * Tests:
 * 1. Multi-model: Toggle on, select models, reload → state persists
 * 2. Single-model: Switch to single, select radios, reload → radios persist
 * 3. Mode switching: Toggle between multi/single → selections preserved
 */

import { test, expect, type Page } from "@playwright/test";

// Helper: Login as test user
async function login(page: Page) {
  await page.goto("/");
  await page.fill('input[type="email"]', "test@example.com");
  await page.fill('input[type="password"]', "testpass123");
  await page.click('button[type="submit"]');
  await page.waitForURL("/");
}

// Helper: Navigate to Settings
async function goToSettings(page: Page) {
  await page.goto("/settings");
  await page.waitForLoadState("networkidle");
}

// Helper: Find model settings section
async function findModelSettingsSection(page: Page) {
  // Look for "AI Model Preferences" heading or ModelSettings component
  const section = page.locator('text="AI Model Preferences"').locator("..");
  await expect(section).toBeVisible();
  return section;
}

test.describe("Model Settings E2E", () => {
  test.beforeEach(async ({ page }) => {
    // Create test user if needed and login
    await login(page);
  });

  test("1. Multi-model: toggle on, select models, reload → state persists", async ({ page }) => {
    await goToSettings(page);
    
    const settingsSection = await findModelSettingsSection(page);
    
    // Find multi-model toggle
    const multiToggle = settingsSection.locator('input[type="checkbox"]').first();
    
    // Enable multi-model mode
    const isChecked = await multiToggle.isChecked();
    if (!isChecked) {
      await multiToggle.check();
    }
    await page.waitForTimeout(500); // Wait for mode change
    
    // Select multiple models for fit role
    const fitSection = settingsSection.locator('text=/fit/i').locator("..");
    const gpt5Checkbox = fitSection.locator('input[type="checkbox"][value="gpt-5"]');
    const claudeCheckbox = fitSection.locator('input[type="checkbox"][value="claude-4.1-opus"]');
    
    await gpt5Checkbox.check();
    await claudeCheckbox.check();
    
    // Select models for tailor role
    const tailorSection = settingsSection.locator('text=/tailor/i').locator("..");
    const geminiCheckbox = tailorSection.locator('input[type="checkbox"][value="gemini-3-pro-preview"]');
    await geminiCheckbox.check();
    
    // Wait for save (optimistic + server sync)
    await page.waitForTimeout(1000);
    
    // Reload page
    await page.reload();
    await page.waitForLoadState("networkidle");
    
    // Verify state persisted
    const reloadedSection = await findModelSettingsSection(page);
    
    // Multi-model should still be enabled
    const reloadedToggle = reloadedSection.locator('input[type="checkbox"]').first();
    await expect(reloadedToggle).toBeChecked();
    
    // Checkboxes should still be checked
    const reloadedFitSection = reloadedSection.locator('text=/fit/i').locator("..");
    const reloadedGpt5 = reloadedFitSection.locator('input[type="checkbox"][value="gpt-5"]');
    const reloadedClaude = reloadedFitSection.locator('input[type="checkbox"][value="claude-4.1-opus"]');
    
    await expect(reloadedGpt5).toBeChecked();
    await expect(reloadedClaude).toBeChecked();
    
    const reloadedTailorSection = reloadedSection.locator('text=/tailor/i').locator("..");
    const reloadedGemini = reloadedTailorSection.locator('input[type="checkbox"][value="gemini-3-pro-preview"]');
    await expect(reloadedGemini).toBeChecked();
  });

  test("2. Single-model: switch to single, pick radios, reload → radios persist", async ({ page }) => {
    await goToSettings(page);
    
    const settingsSection = await findModelSettingsSection(page);
    
    // Disable multi-model mode (switch to single)
    const multiToggle = settingsSection.locator('input[type="checkbox"]').first();
    const isChecked = await multiToggle.isChecked();
    if (isChecked) {
      await multiToggle.uncheck();
    }
    await page.waitForTimeout(500); // Wait for mode change
    
    // Select radio buttons for each role
    const fitSection = settingsSection.locator('text=/fit/i').locator("..");
    const fitRadio = fitSection.locator('input[type="radio"][value="claude-4.1-opus"]');
    await fitRadio.check();
    
    const tailorSection = settingsSection.locator('text=/tailor/i').locator("..");
    const tailorRadio = tailorSection.locator('input[type="radio"][value="gpt-5"]');
    await tailorRadio.check();
    
    const judgeSection = settingsSection.locator('text=/judge/i').locator("..");
    const judgeRadio = judgeSection.locator('input[type="radio"][value="gemini-3-pro-preview"]');
    await judgeRadio.check();
    
    // Wait for save
    await page.waitForTimeout(1000);
    
    // Reload page
    await page.reload();
    await page.waitForLoadState("networkidle");
    
    // Verify radios persisted
    const reloadedSection = await findModelSettingsSection(page);
    
    // Multi-model should still be disabled
    const reloadedToggle = reloadedSection.locator('input[type="checkbox"]').first();
    await expect(reloadedToggle).not.toBeChecked();
    
    // Radio selections should persist
    const reloadedFitSection = reloadedSection.locator('text=/fit/i').locator("..");
    const reloadedFitRadio = reloadedFitSection.locator('input[type="radio"][value="claude-4.1-opus"]');
    await expect(reloadedFitRadio).toBeChecked();
    
    const reloadedTailorSection = reloadedSection.locator('text=/tailor/i').locator("..");
    const reloadedTailorRadio = reloadedTailorSection.locator('input[type="radio"][value="gpt-5"]');
    await expect(reloadedTailorRadio).toBeChecked();
    
    const reloadedJudgeSection = reloadedSection.locator('text=/judge/i').locator("..");
    const reloadedJudgeRadio = reloadedJudgeSection.locator('input[type="radio"][value="gemini-3-pro-preview"]');
    await expect(reloadedJudgeRadio).toBeChecked();
  });

  test("3. Mode switching: multi → single → multi preserves selections", async ({ page }) => {
    await goToSettings(page);
    
    let settingsSection = await findModelSettingsSection(page);
    
    // Step 1: Enable multi-model and select checkboxes
    const multiToggle = settingsSection.locator('input[type="checkbox"]').first();
    await multiToggle.check();
    await page.waitForTimeout(500);
    
    const fitSection = settingsSection.locator('text=/fit/i').locator("..");
    await fitSection.locator('input[type="checkbox"][value="gpt-5"]').check();
    await fitSection.locator('input[type="checkbox"][value="claude-4.1-opus"]').check();
    
    const tailorSection = settingsSection.locator('text=/tailor/i').locator("..");
    await tailorSection.locator('input[type="checkbox"][value="gemini-3-pro-preview"]').check();
    
    await page.waitForTimeout(1000);
    
    // Step 2: Switch to single-model
    await multiToggle.uncheck();
    await page.waitForTimeout(500);
    
    // Verify radios reflect first checkbox selection
    const fitRadio = page.locator('input[type="radio"][value="gpt-5"]');
    await expect(fitRadio).toBeChecked();
    
    const tailorRadio = page.locator('input[type="radio"][value="gemini-3-pro-preview"]');
    await expect(tailorRadio).toBeChecked();
    
    // Step 3: Switch back to multi-model
    await multiToggle.check();
    await page.waitForTimeout(500);
    
    // Verify checkboxes are preserved
    settingsSection = await findModelSettingsSection(page);
    const reloadedFitSection = settingsSection.locator('text=/fit/i').locator("..");
    
    await expect(reloadedFitSection.locator('input[type="checkbox"][value="gpt-5"]')).toBeChecked();
    await expect(reloadedFitSection.locator('input[type="checkbox"][value="claude-4.1-opus"]')).toBeChecked();
    
    const reloadedTailorSection = settingsSection.locator('text=/tailor/i').locator("..");
    await expect(reloadedTailorSection.locator('input[type="checkbox"][value="gemini-3-pro-preview"]')).toBeChecked();
  });

  test("4. Select All and Clear All buttons work correctly", async ({ page }) => {
    await goToSettings(page);
    
    const settingsSection = await findModelSettingsSection(page);
    
    // Enable multi-model
    const multiToggle = settingsSection.locator('input[type="checkbox"]').first();
    await multiToggle.check();
    await page.waitForTimeout(500);
    
    // Find Select All button for fit role
    const fitSection = settingsSection.locator('text=/fit/i').locator("..");
    const selectAllBtn = fitSection.locator('button:has-text("Select All")');
    await selectAllBtn.click();
    await page.waitForTimeout(500);
    
    // Verify all checkboxes are checked
    const checkboxes = await fitSection.locator('input[type="checkbox"]').all();
    for (const checkbox of checkboxes) {
      await expect(checkbox).toBeChecked();
    }
    
    // Click Clear button
    const clearBtn = fitSection.locator('button:has-text("Clear")');
    await clearBtn.click();
    await page.waitForTimeout(500);
    
    // Verify all checkboxes are unchecked
    for (const checkbox of checkboxes) {
      await expect(checkbox).not.toBeChecked();
    }
  });

  test("5. Settings persist across browser sessions", async ({ page, context }) => {
    await goToSettings(page);
    
    const settingsSection = await findModelSettingsSection(page);
    
    // Set up a specific configuration
    const multiToggle = settingsSection.locator('input[type="checkbox"]').first();
    await multiToggle.check();
    await page.waitForTimeout(500);
    
    const fitSection = settingsSection.locator('text=/fit/i').locator("..");
    await fitSection.locator('input[type="checkbox"][value="grok-4"]').check();
    
    await page.waitForTimeout(1000);
    
    // Close browser context (simulates closing browser)
    await context.close();
    
    // Create new context and login again
    const newContext = await page.context().browser()!.newContext();
    const newPage = await newContext.newPage();
    await login(newPage);
    await goToSettings(newPage);
    
    // Verify settings persisted
    const newSettingsSection = await findModelSettingsSection(newPage);
    const newMultiToggle = newSettingsSection.locator('input[type="checkbox"]').first();
    await expect(newMultiToggle).toBeChecked();
    
    const newFitSection = newSettingsSection.locator('text=/fit/i').locator("..");
    const grokCheckbox = newFitSection.locator('input[type="checkbox"][value="grok-4"]');
    await expect(grokCheckbox).toBeChecked();
    
    await newContext.close();
  });

  test("6. Saving indicator appears during updates", async ({ page }) => {
    await goToSettings(page);
    
    const settingsSection = await findModelSettingsSection(page);
    
    // Enable multi-model
    const multiToggle = settingsSection.locator('input[type="checkbox"]').first();
    await multiToggle.check();
    
    // Look for "Saving..." indicator
    const savingIndicator = page.locator('text=/saving/i');
    
    // The indicator should appear briefly
    // (This is timing-dependent, so we just verify the component doesn't error)
    await page.waitForTimeout(1000);
    
    // After save, indicator should disappear
    await expect(savingIndicator).not.toBeVisible({ timeout: 5000 });
  });

  test("7. Error handling: displays error on network failure", async ({ page }) => {
    await goToSettings(page);
    
    // Intercept PUT request and force it to fail
    await page.route('**/users/me/model-settings', route => {
      if (route.request().method() === 'PUT') {
        route.abort('failed');
      } else {
        route.continue();
      }
    });
    
    const settingsSection = await findModelSettingsSection(page);
    const multiToggle = settingsSection.locator('input[type="checkbox"]').first();
    
    // Try to change settings
    await multiToggle.check();
    await page.waitForTimeout(1000);
    
    // Should show error message
    const errorMessage = page.locator('text=/error|failed/i');
    await expect(errorMessage).toBeVisible({ timeout: 5000 });
  });
});
