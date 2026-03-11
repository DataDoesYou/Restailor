import { test, expect } from "@playwright/test";

test.describe("Pinnacle UI", () => {
  test("labels toggle and filter work", async ({ page }) => {
    await page.goto("http://localhost:3000/pinnacle");

    // Toggle labels via toolbar link (?labels=1)
    await page.getByTestId("toolbar-toggle-labels").click();
    await expect(page).toHaveURL(/labels=1/);

    // A known tag should appear and focusing works
    const firstTag = page.getByText("Hero: Hero Header").first();
    await expect(firstTag).toBeVisible();
    await firstTag.click();
    await expect(page.getByTestId("hero-title")).toBeFocused();

  // Filter with q=Primary – only matching elements remain in Actions
    await page.goto("http://localhost:3000/pinnacle?q=Primary&labels=1");
    await expect(page.getByTestId("act-primary")).toBeVisible();
    await expect(page.getByTestId("act-secondary")).toHaveCount(0);

  // Form submit echoes data
  await page.goto("http://localhost:3000/pinnacle");
  await page.getByTestId("form-email").fill("a@b.com");
  await page.getByTestId("form-name").fill("Ada");
  await page.getByTestId("form-submit").click();
  await expect(page.locator("pre", { hasText: '"submitted"' })).toBeVisible();
  });
});
