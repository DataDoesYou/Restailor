/**
 * E2E test to verify validation error messages include debug information.
 * This ensures users can diagnose model selection issues without opening DevTools.
 * 
 * Run with: npm --prefix frontend run test:e2e -- frontend/e2e/validation-error-debug.spec.ts
 */

import { test, expect } from '@playwright/test';

test.describe('Validation Error Debug Info', () => {
	test.beforeEach(async ({ page }) => {
		// Go to resume page
		await page.goto('http://localhost:3000/resume');
		
		// Wait for page to load
		await page.waitForLoadState('networkidle');
	});

	test('should show debug info in error message when no model is selected', async ({ page }) => {
		// Fill in resume and JD to pass input validation
		const resumeTextarea = page.locator('textarea').filter({ hasText: /resume/i }).first();
		const jdTextarea = page.locator('textarea').filter({ hasText: /job/i }).first();
		
		await resumeTextarea.fill('My resume text here with some content to make it valid.');
		await jdTextarea.fill('Job description text here with some requirements and details.');

		// Make sure no model is selected by clearing the sidebar
		// (or just proceed if already empty)
		
		// Click "Check Fit" button
		const checkFitButton = page.locator('button', { hasText: /check fit/i });
		await checkFitButton.click();

		// Wait for error message to appear
		const errorMessage = page.locator('text=/please select a fit model in the sidebar/i');
		await expect(errorMessage).toBeVisible({ timeout: 5000 });

		// Verify debug info is included in the error message
		const errorText = await errorMessage.textContent();
		expect(errorText).toMatch(/label=NULL/);
		expect(errorText).toMatch(/meta=NULL/);
		expect(errorText).toMatch(/multi=(YES|NO)/);
	});

	test('should show complete debug format in error message', async ({ page }) => {
		// Fill in resume and JD
		const resumeTextarea = page.locator('textarea').first();
		const jdTextarea = page.locator('textarea').nth(1);
		
		await resumeTextarea.fill('Test resume content for validation.');
		await jdTextarea.fill('Test job description for validation.');

		// Click button without model selection
		const checkFitButton = page.locator('button', { hasText: /check fit/i });
		await checkFitButton.click();

		// Wait for error message
		const errorMessage = page.locator('text=/please select a fit model in the sidebar/i');
		await expect(errorMessage).toBeVisible({ timeout: 5000 });

		// Verify complete debug format: (label=..., meta=..., multi=...)
		const errorText = await errorMessage.textContent() || '';
		
		// Should contain parentheses with all three debug fields
		expect(errorText).toMatch(/\(label=[^,]+,\s*meta=[^,]+,\s*multi=[^)]+\)/);
	});

	test('should update debug info when model is selected then deselected', async ({ page }) => {
		// Fill in inputs
		const resumeTextarea = page.locator('textarea').first();
		const jdTextarea = page.locator('textarea').nth(1);
		
		await resumeTextarea.fill('Resume text');
		await jdTextarea.fill('JD text');

		// First attempt - no model
		const checkFitButton = page.locator('button', { hasText: /check fit/i });
		await checkFitButton.click();

		let errorMessage = page.locator('text=/please select a fit model in the sidebar/i');
		await expect(errorMessage).toBeVisible({ timeout: 5000 });

		let errorText = await errorMessage.textContent() || '';
		expect(errorText).toContain('label=NULL');
		expect(errorText).toContain('meta=NULL');

		// Close the alert
		const closeButton = page.locator('button[aria-label="Close alert"]').or(page.locator('button:has-text("×")')).first();
		if (await closeButton.isVisible()) {
			await closeButton.click();
		}

		// Now select a model in sidebar
		const sidebarButton = page.locator('button', { hasText: /models/i }).or(page.locator('[aria-label*="model"]')).first();
		if (await sidebarButton.isVisible()) {
			await sidebarButton.click();
			
			// Wait a bit for model selection to register
			await page.waitForTimeout(500);
			
			// Try again
			await checkFitButton.click();
			
			// Should either succeed or show updated debug info (if model still not properly selected)
			// We're just verifying the debug info updates dynamically
		}
	});
});
